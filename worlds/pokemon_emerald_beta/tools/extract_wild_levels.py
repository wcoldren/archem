#!/usr/bin/env python3
"""
Generate ``wild_levels.json``: each map's vanilla wild-encounter levels, per slot, derived from
the Pokemon Emerald base-patch decomp.

The C++ extractor (``vendor/emerald-archipelago/tools/extractor``) reads per-slot min/max levels
from ``src/data/wild_encounters.json`` but its ``to_json`` only emits species, so the apworld's
``extracted_data.json`` carries ``{address, slots}`` with no levels. This table backfills the
vanilla levels so level scaling can use them as the basis for the ``vanilla`` curve mode (and so
the per-slot vanilla spread is available at all). It is loaded as augmentation in ``data.py`` and
joined onto ``EncounterTableData`` by ``(MAP_, source)``; a missing file just leaves levels absent.

The decomp groups encounters under ``wild_encounter_groups``. Only the first group
(``gWildMonHeaders``, the normal overworld) is relevant; the Battle Pyramid/Pike groups are
runtime-generated and have no scaled-encounter address in the apworld. Each map entry looks like::

    {"map": "MAP_ROUTE101", "base_label": "gRoute101",
     "land_mons": {"encounter_rate": 20, "mons": [{"min_level": 2, "max_level": 2, "species": "..."}, ...]}}

The ``mons`` order matches the extractor's slot order (same source file), so the emitted level
lists are index-aligned with ``EncounterTableData.slots``.

Run from anywhere; by default it finds the sibling decomp checkout. Output is deterministic
(sorted keys), so regenerating produces a byte-identical file.

    python extract_wild_levels.py [--encounters PATH] [--out PATH] [--quiet]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# decomp ``*_mons`` category -> the short key used in wild_levels.json (and matched to PokemonSource
# in data.py). Order here is the canonical output order.
_CATEGORIES = (
    ("land_mons", "land"),
    ("water_mons", "water"),
    ("fishing_mons", "fishing"),
    ("rock_smash_mons", "rock_smash"),
)


def _default_encounters() -> Path:
    # This file lives at .../vendor/archem/worlds/pokemon_emerald_beta/tools/extract_wild_levels.py
    # The decomp is a sibling clone at .../vendor/emerald-archipelago/src/data/wild_encounters.json.
    here = Path(__file__).resolve()
    vendor = here.parents[4]  # .../vendor
    return vendor / "emerald-archipelago" / "src" / "data" / "wild_encounters.json"


def extract(encounters_path: Path) -> tuple[dict[str, dict], list[str]]:
    """Return ({MAP_: {category: [[min, max], ...]}}, warnings)."""
    warnings: list[str] = []
    raw = json.loads(encounters_path.read_text(encoding="utf-8"))
    groups = raw.get("wild_encounter_groups", [])
    if not groups:
        warnings.append("no wild_encounter_groups in source")
        return {}, warnings

    # gWildMonHeaders is the normal overworld group; ignore Battle Pyramid/Pike.
    overworld = next((g for g in groups if g.get("label") == "gWildMonHeaders"), groups[0])

    table: dict[str, dict] = {}
    dupes: set[str] = set()
    for entry in overworld.get("encounters", []):
        map_id = entry.get("map")
        if not map_id:
            continue
        levels: dict[str, list] = {}
        for src_key, out_key in _CATEGORIES:
            section = entry.get(src_key)
            if not section:
                continue
            levels[out_key] = [[mon["min_level"], mon["max_level"]] for mon in section["mons"]]
        if not levels:
            continue
        if map_id in table:
            # A few maps (e.g. MAP_ALTERING_CAVE) carry several alternate tables in the decomp;
            # keep the first and note the map once.
            if map_id not in dupes:
                dupes.add(map_id)
                warnings.append(f"{map_id} has multiple tables; keeping first")
            continue
        table[map_id] = levels

    return dict(sorted(table.items())), warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--encounters", type=Path, default=_default_encounters(),
                        help="decomp src/data/wild_encounters.json (default: sibling emerald-archipelago checkout)")
    parser.add_argument("--out", type=Path,
                        default=Path(__file__).resolve().parent.parent / "data" / "wild_levels.json",
                        help="output JSON path (default: ../data/wild_levels.json, the world data dir)")
    parser.add_argument("--quiet", action="store_true", help="suppress the summary report")
    args = parser.parse_args()

    if not args.encounters.is_file():
        print(f"ERROR: wild_encounters.json not found: {args.encounters}", file=sys.stderr)
        return 1

    table, warnings = extract(args.encounters)
    args.out.write_text(json.dumps(table, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

    if not args.quiet:
        slots = sum(len(slot_list) for cats in table.values() for slot_list in cats.values())
        tables = sum(len(cats) for cats in table.values())
        print(f"wrote {args.out}")
        print(f"  maps with wild levels : {len(table)}")
        print(f"  encounter tables      : {tables}")
        print(f"  total slots           : {slots}")
        if warnings:
            print(f"  warnings              : {len(warnings)}")
            for w in warnings[:20]:
                print(f"    - {w}")
            if len(warnings) > 20:
                print(f"    ... and {len(warnings) - 20} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
