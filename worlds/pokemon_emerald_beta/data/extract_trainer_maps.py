#!/usr/bin/env python3
"""
Generate ``trainer_map.json``: a map from each overworld-scripted trainer constant to the
game MAP it is fought on, derived from the Pokemon Emerald base-patch decomp.

This is the "option C" data source for full trainer-region coverage in sphere-based level
scaling (see ``dev/region_map_scoping.md``). The apworld's primary trainer->region source is
each trainer's ``TRAINER_<NAME>_REWARD`` location; this table is a fallback so trainers without
a reward location (scripted specials, multi-map grunts, rival variants, etc.) still get a region
and therefore get scaled. Battle Frontier brains are intentionally absent (they are
runtime-generated and have no ``Archipelago_Target_`` label).

The decomp tags each scripted trainer with a label on the line(s) before its battle macro:

    Route103_EventScript_Daisy::
    Archipelago_Target_TRAINER_DAISY::
        trainerbattle_single TRAINER_DAISY, ...

We key on the ``Archipelago_Target_TRAINER_<NAME>::`` label, take the following ``trainerbattle*``
macro to learn the battle variant, and resolve the map id from ``<MapDir>/map.json``.

Run from anywhere; by default it finds the sibling decomp checkout. Output is deterministic
(sorted keys), so regenerating produces a byte-identical file.

    python extract_trainer_maps.py [--maps-dir PATH] [--out PATH] [--quiet]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Label that tags a scripted trainer battle, e.g. "Archipelago_Target_TRAINER_DAISY::".
LABEL_RE = re.compile(r"^\s*Archipelago_Target_(TRAINER_[A-Z0-9_]+)::")
# A trainerbattle* macro line; capture the macro variant and its first TRAINER_ argument.
# Note: the generic "trainerbattle TRAINER_BATTLE_*, TRAINER_<brain>, ..." Frontier form has no
# Archipelago_Target_ label, so we never reach it via the label scan above.
BATTLE_RE = re.compile(r"^\s*(trainerbattle\w*)\s+(TRAINER_[A-Z0-9_]+)")

# The battle-macro variants that denote a rematch. This is the ONLY reliable rematch signal:
# the numeric "_<N>" suffix is overloaded (e.g. TRAINER_GRUNT_AQUA_HIDEOUT_1..8 are eight
# DISTINCT grunts, not a ladder), so we must not infer rematches from the constant name. In
# practice the true Match Call gym rematches (TRAINER_<LEADER>_2..5) carry no Archipelago_Target_
# label at all — they are runtime-generated — so they never enter this table and stay vanilla by
# omission. This guard simply future-proofs against a labeled rematch ever appearing.
REMATCH_MACROS = {"trainerbattle_rematch", "trainerbattle_rematch_double"}


def _default_maps_dir() -> Path:
    # This file lives at .../vendor/archem/worlds/pokemon_emerald_beta/data/extract_trainer_maps.py
    # The decomp is a sibling clone at .../vendor/emerald-archipelago/data/maps.
    here = Path(__file__).resolve()
    vendor = here.parents[4]  # .../vendor
    return vendor / "emerald-archipelago" / "data" / "maps"


def _map_id(map_dir: Path) -> str | None:
    """Read the MAP_ constant for a decomp map directory from its map.json 'id' field."""
    map_json = map_dir / "map.json"
    if not map_json.is_file():
        return None
    try:
        return json.loads(map_json.read_text(encoding="utf-8")).get("id")
    except (ValueError, OSError):
        return None


def extract(maps_dir: Path) -> tuple[dict[str, dict], list[str]]:
    """Return ({TRAINER_X: {"map": MAP_, "rematch": bool}}, warnings)."""
    warnings: list[str] = []
    # (trainer_const, map_id, macro) tuples in scan order.
    raw: list[tuple[str, str, str | None]] = []

    for map_dir in sorted(p for p in maps_dir.iterdir() if p.is_dir()):
        scripts = map_dir / "scripts.inc"
        if not scripts.is_file():
            continue
        map_id = _map_id(map_dir)
        if map_id is None:
            warnings.append(f"no map id for {map_dir.name}")
            continue
        lines = scripts.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            label = LABEL_RE.match(line)
            if not label:
                continue
            const = label.group(1)
            # Find the trainer battle macro that follows this label (normally the next line).
            macro: str | None = None
            for follow in lines[i + 1:i + 11]:
                battle = BATTLE_RE.match(follow)
                if battle:
                    macro = battle.group(1)
                    break
            raw.append((const, map_id, macro))

    table: dict[str, dict] = {}
    for const, map_id, macro in raw:
        is_rematch = macro in REMATCH_MACROS
        if const in table:
            # Same trainer labeled on multiple maps: keep first (deterministic via sorted dirs),
            # but don't let a later rematch appearance flip an earlier first-battle mapping.
            if is_rematch and not table[const]["rematch"]:
                continue
            warnings.append(f"{const} appears on multiple maps ({table[const]['map']}, {map_id})")
            continue
        table[const] = {"map": map_id, "rematch": is_rematch}

    return dict(sorted(table.items())), warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--maps-dir", type=Path, default=_default_maps_dir(),
                        help="decomp data/maps directory (default: sibling emerald-archipelago checkout)")
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "trainer_map.json",
                        help="output JSON path (default: ./trainer_map.json next to this script)")
    parser.add_argument("--quiet", action="store_true", help="suppress the summary report")
    args = parser.parse_args()

    if not args.maps_dir.is_dir():
        print(f"ERROR: maps dir not found: {args.maps_dir}", file=sys.stderr)
        return 1

    table, warnings = extract(args.maps_dir)
    # Trailing newline; sorted keys already applied. Compact-ish but diff-friendly.
    args.out.write_text(json.dumps(table, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

    if not args.quiet:
        rematches = sum(1 for v in table.values() if v["rematch"])
        print(f"wrote {args.out}")
        print(f"  trainers mapped : {len(table)}")
        print(f"  rematch-flagged : {rematches} (excluded from scaling by default)")
        print(f"  non-rematch     : {len(table) - rematches} (eligible as a region fallback; "
              "many already covered by their reward location)")
        if warnings:
            print(f"  warnings        : {len(warnings)}")
            for w in warnings[:20]:
                print(f"    - {w}")
            if len(warnings) > 20:
                print(f"    ... and {len(warnings) - 20} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
