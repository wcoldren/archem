#!/usr/bin/env python3
"""
Generate ``misc_levels.json``: the vanilla level of each misc/gift Pokemon, derived from the
Pokemon Emerald base-patch decomp scripts.

``extracted_data.json`` carries ``misc_pokemon`` as ``{address, species}`` with no level (only
``legendary_encounters`` carry one). This table backfills the vanilla level onto
``MiscPokemonData.level`` -- the extraction half of misc/gift level scaling.

NOTE: this is the enabler, not the whole feature. Unlike legendaries, a misc ``address`` points at
a species field in an object-event/static table, NOT a ``setwildbattle``/``givemon`` operand, so
``address + 2`` is not the level (verified against the base ROM: even the Castform gift reads a
non-level byte there). So while we now know each misc Pokemon's vanilla level, there is still no
known ROM address at which to WRITE a scaled one -- misc scaling stays blocked until the
level-operand addresses are extracted. See scaling.py.

The misc ``address`` therefore can't give us the level either; instead we read the human-readable
level from the decomp scripts, where each static/gift is written as ``setwildbattle SPECIES_X,
LEVEL`` or ``givemon SPECIES_X, LEVEL, ...``.

The misc set is small and each species' vanilla level is consistent across all its sites
(Kecleon 30, Voltorb 25, Electrode 30, Sudowoodo 40, Castform 25), so a species -> level map from
the scripts is sufficient and unambiguous. A species with conflicting levels across sites is
reported and skipped (left unscaled) rather than guessed. ``giveegg`` gifts (Wynaut) have no level
and are intentionally omitted -- eggs hatch at a fixed level regardless of scaling.

Output is keyed by ``misc_pokemon`` address (so ``data.py`` can populate ``MiscPokemonData.level``
by address with no species lookup). Loaded as augmentation in ``data.py``; a missing file just
leaves misc levels absent (misc scaling then no-ops). Deterministic (sorted) output.

    python extract_misc_levels.py [--scripts-root PATH] [--extracted PATH] [--out PATH] [--quiet]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

# setwildbattle SPECIES_X, LEVEL[, ...]   /   givemon SPECIES_X, LEVEL[, ...]
LEVEL_RE = re.compile(r"\b(?:setwildbattle|givemon)\s+(SPECIES_[A-Z0-9_]+)\s*,\s*(\d+)")


def _default_scripts_root() -> Path:
    # This file lives at .../vendor/archem/worlds/pokemon_emerald_beta/tools/extract_misc_levels.py
    # The decomp is a sibling clone at .../vendor/emerald-archipelago.
    here = Path(__file__).resolve()
    vendor = here.parents[4]  # .../vendor
    return vendor / "emerald-archipelago"


def _default_extracted() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "extracted_data.json"


def _scan_species_levels(scripts_root: Path) -> dict[str, set[int]]:
    """Scan decomp .inc scripts for setwildbattle/givemon -> {SPECIES_X: {levels}}."""
    species_levels: dict[str, set[int]] = defaultdict(set)
    for inc in scripts_root.rglob("*.inc"):
        try:
            text = inc.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for species, level in LEVEL_RE.findall(text):
            species_levels[species].add(int(level))
    return species_levels


def extract(scripts_root: Path, misc_pokemon: list[dict], constants: dict[str, int]
            ) -> tuple[dict[str, int], list[str]]:
    """Return ({str(address): level}, warnings), keyed by the misc_pokemon address."""
    warnings: list[str] = []
    species_levels = _scan_species_levels(scripts_root)
    id_to_name = {v: k for k, v in constants.items() if k.startswith("SPECIES_")}

    table: dict[str, int] = {}
    for entry in misc_pokemon:
        species_name = id_to_name.get(entry["species"])
        levels = species_levels.get(species_name) if species_name else None
        if not levels:
            warnings.append(f"{species_name or entry['species']} @ {entry['address']}: "
                            "no setwildbattle/givemon level in scripts (e.g. egg gift); skipped")
            continue
        if len(levels) > 1:
            warnings.append(f"{species_name}: conflicting levels {sorted(levels)} across sites; skipped")
            continue
        table[str(entry["address"])] = next(iter(levels))

    return dict(sorted(table.items(), key=lambda kv: int(kv[0]))), warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scripts-root", type=Path, default=_default_scripts_root(),
                        help="decomp root to scan for *.inc (default: sibling emerald-archipelago checkout)")
    parser.add_argument("--extracted", type=Path, default=_default_extracted(),
                        help="extracted_data.json providing misc_pokemon + species constants")
    parser.add_argument("--out", type=Path,
                        default=Path(__file__).resolve().parent.parent / "data" / "misc_levels.json",
                        help="output JSON path (default: ../data/misc_levels.json, the world data dir)")
    parser.add_argument("--quiet", action="store_true", help="suppress the summary report")
    args = parser.parse_args()

    if not args.scripts_root.is_dir():
        print(f"ERROR: decomp scripts root not found: {args.scripts_root}", file=sys.stderr)
        return 1
    if not args.extracted.is_file():
        print(f"ERROR: extracted_data.json not found: {args.extracted}", file=sys.stderr)
        return 1

    extracted = json.loads(args.extracted.read_text(encoding="utf-8-sig"))
    misc_pokemon = extracted.get("misc_pokemon", [])
    constants = extracted.get("constants", {})

    table, warnings = extract(args.scripts_root, misc_pokemon, constants)
    args.out.write_text(json.dumps(table, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

    if not args.quiet:
        print(f"wrote {args.out}")
        print(f"  misc pokemon     : {len(misc_pokemon)}")
        print(f"  levels extracted : {len(table)}")
        if warnings:
            print(f"  skipped          : {len(warnings)}")
            for w in warnings[:20]:
                print(f"    - {w}")
            if len(warnings) > 20:
                print(f"    ... and {len(warnings) - 20} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
