"""
Sphere-based level scaling for Pokemon Emerald (trainers + wild encounters + legendaries).

Called from PokemonEmeraldWorld.generate_output(), AFTER randomize_opponent_parties() /
randomize_wild_encounters() / randomize_legendary_encounters() (so species and vanilla levels
exist) and BEFORE write_tokens() builds the patch.

Approach (adapted from the Pokemon Crystal Archipelago level-scaling implementation by
cheerioschelsea — PR #127 "Implement Sphere Based Level Scaling" — and James White): each
category is ordered by logical progression depth (the sphere in which its region first becomes
reachable, then by vanilla strength) and a curve of target levels from the configured min to max
is distributed across it by rank.

- Trainers: each party is rescaled to its target while preserving its internal level spread.
  Trainers without a TRAINER reward location have no region data and are left at vanilla levels
  (this covers rematches and Battle Frontier brains, matching Crystal's default of excluding
  rematches).
- Wild encounters: each encounter table is mapped to its map's region, ranked by sphere, and
  flattened to a single scaled level applied to every slot (Crystal-style; preserving vanilla
  per-slot spread would require the extractor to emit vanilla min/max levels, which it does not).
  Tables whose map has no reachable region are left vanilla.
- Legendaries: ranked by their vanilla level as a progression proxy (legendaries carry no region
  link, only an address), then assigned the curve by rank. Misc/gift Pokemon are not scaled — the
  extracted data carries no vanilla level for them.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from BaseClasses import CollectionState

from .data import data, LocationCategory, PokemonSource
from .options import LevelScalingCurve

if TYPE_CHECKING:
    from .world import PokemonEmeraldWorld


def _generate_curve_levels(n: int, min_level: int, max_level: int, shape: int) -> list[int]:
    """
    Distribute n levels from min_level to max_level along the given curve shape.
    Ported from the Pokemon Crystal implementation (regions.py `_generate_curve_levels`).
    """
    if n <= 0:
        return []
    if n == 1:
        return [min_level]
    lo, hi = min(min_level, max_level), max(min_level, max_level)
    span = hi - lo
    levels = []
    for i in range(n):
        t = i / (n - 1)
        if shape == LevelScalingCurve.option_sqrt:
            t = t ** 0.5
        elif shape == LevelScalingCurve.option_quadratic:
            t = t ** 2
        elif shape == LevelScalingCurve.option_s_curve:
            t = t * t * (3 - 2 * t)  # smoothstep
        levels.append(round(lo + span * t))
    return levels


def _compute_region_spheres(world: "PokemonEmeraldWorld") -> dict[str, int]:
    """
    Record the earliest sphere in which each of this player's regions becomes reachable.
    Uses region reachability (not location spheres) so regions with no live locations
    still get a sphere — important when Trainersanity is off.
    """
    multiworld = world.multiworld
    state = CollectionState(multiworld)
    region_sphere: dict[str, int] = {}

    unchecked = {loc for loc in multiworld.get_locations() if loc.item is not None}

    sphere = 0
    while True:
        for region in multiworld.get_regions(world.player):
            if region.name not in region_sphere and region.can_reach(state):
                region_sphere[region.name] = sphere

        reachable = {loc for loc in unchecked if loc.can_reach(state)}
        if not reachable:
            break
        for loc in reachable:
            # collect() marks the player's reachability stale regardless of prevent_sweep,
            # so the next region.can_reach() recomputes and reachability cascades.
            state.collect(loc.item, prevent_sweep=True)
        unchecked -= reachable
        sphere += 1

    return region_sphere


def _build_map_to_regions() -> dict[str, list[str]]:
    """map name (MAP_*) -> the AP region names that belong to it."""
    map_to_regions: dict[str, list[str]] = {}
    for region_name, region_data in data.regions.items():
        parent_map = getattr(region_data, "parent_map", None)
        if parent_map is not None:
            map_to_regions.setdefault(parent_map.name, []).append(region_name)
    return map_to_regions


def _representative_region(map_to_regions: dict[str, list[str]], map_id: str) -> "str | None":
    """
    Pick one region to represent a whole map for sphere purposes. Sub-region sphere differences
    within one map are 0-1, so a representative suffices: prefer the map's main region, else the
    lexicographically-first region. Returns None for maps with no AP region (cut/unused).
    """
    regions = sorted(map_to_regions.get(map_id, []))
    if not regions:
        return None
    for region in regions:
        if region.endswith("/MAIN"):
            return region
    return regions[0]


def _build_trainer_region_map(world: "PokemonEmeraldWorld") -> dict[int, str]:
    """
    trainer index in world.modified_trainers -> parent region name.

    Primary source: each trainer's TRAINER_<NAME>_REWARD location (sub-region accurate). The six
    Route-103-style rival battles are merged in data.py into a single canonical location keyed on
    the BRENDAN ..._MUDKIP variant, so the other five variant trainers (the one the player
    actually fights depends on gender + starter) would otherwise be unmapped. Map all sibling
    variants to the same region so whichever rival is fought gets scaled.

    Fallback source: the decomp-derived trainer->map table (data.trainer_map, see
    data/extract_trainer_maps.py) covers trainers with no reward location (scripted specials,
    multi-map grunts, etc.). Rematches are excluded by default, matching Pokemon Crystal; true
    Match Call rematches carry no decomp battle label and so never appear in the table regardless.
    """
    trainer_region: dict[int, str] = {}
    for loc_name, loc_data in data.locations.items():
        if loc_data.category != LocationCategory.TRAINER:
            continue
        trainer_const = loc_name.removesuffix("_REWARD")
        idx = data.constants.get(trainer_const)
        if idx is not None:
            trainer_region[idx] = loc_data.parent_region

        # Expand merged rival locations to all sibling variant trainers.
        rival_match = re.match(r"TRAINER_BRENDAN_([A-Z0-9_]+)_MUDKIP$", trainer_const)
        if rival_match:
            locale = rival_match.group(1)
            for sibling in (
                f"TRAINER_BRENDAN_{locale}_TORCHIC",
                f"TRAINER_BRENDAN_{locale}_TREECKO",
                f"TRAINER_MAY_{locale}_MUDKIP",
                f"TRAINER_MAY_{locale}_TORCHIC",
                f"TRAINER_MAY_{locale}_TREECKO",
            ):
                sibling_idx = data.constants.get(sibling)
                if sibling_idx is not None:
                    trainer_region[sibling_idx] = loc_data.parent_region

    # Fallback: fill trainers still unmapped from the decomp trainer->map table.
    if data.trainer_map:
        map_to_regions = _build_map_to_regions()
        for trainer_const, entry in data.trainer_map.items():
            if entry.get("rematch"):  # excluded by default; future opt-in flips this guard
                continue
            idx = data.constants.get(trainer_const)
            if idx is None or idx in trainer_region:
                continue
            region = _representative_region(map_to_regions, entry["map"])
            if region is not None:
                trainer_region[idx] = region

    return trainer_region


def perform_level_scaling(world: "PokemonEmeraldWorld") -> None:
    region_sphere = _compute_region_spheres(world)
    min_level = world.options.level_scaling_min_level.value
    max_level = world.options.level_scaling_max_level.value
    curve = world.options.level_scaling_curve.value

    _scale_trainers(world, region_sphere, min_level, max_level, curve)
    _scale_wild_encounters(world, region_sphere, min_level, max_level, curve)
    _scale_legendary_encounters(world, min_level, max_level, curve)


def _scale_trainers(world: "PokemonEmeraldWorld", region_sphere: dict[str, int],
                    min_level: int, max_level: int, curve: int) -> None:
    trainer_region = _build_trainer_region_map(world)

    # Gather every scaled trainer with its progression depth and vanilla ace level.
    scaled: list[tuple[int, int, int]] = []  # (sphere, old_base, idx)
    for idx, region_name in trainer_region.items():
        sphere = region_sphere.get(region_name)
        if sphere is None:
            continue  # region never reached -> leave this trainer vanilla
        party = world.modified_trainers[idx].party.pokemon
        if not party:
            continue
        old_base = max(mon.level for mon in party)
        if old_base <= 0:
            continue
        scaled.append((sphere, old_base, idx))

    if not scaled:
        return

    # Order by progression depth, then vanilla strength, then index (deterministic), and
    # distribute the level curve across the trainers by rank.
    scaled.sort()
    targets = _generate_curve_levels(len(scaled), min_level, max_level, curve)

    for (_sphere, old_base, idx), target in zip(scaled, targets):
        trainer = world.modified_trainers[idx]
        new_party = []
        for mon in trainer.party.pokemon:
            # Spread-preserving formula (from Crystal): the ace lands on the target and the
            # rest scale proportionally below it, keeping the team's internal spread.
            new_level = round(min(
                target * mon.level / old_base,
                target + mon.level - old_base,
            ))
            new_level = max(1, min(100, new_level))
            new_party.append(mon._replace(level=new_level))  # TrainerPokemonData is a NamedTuple

        trainer.party = trainer.party._replace(pokemon=new_party)


def _scale_wild_encounters(world: "PokemonEmeraldWorld", region_sphere: dict[str, int],
                           min_level: int, max_level: int, curve: int) -> None:
    """
    Rank each wild encounter table by the sphere of its map's region and flatten it to a single
    scaled level (written to every slot's min == max by rom.py). Tables whose map has no reachable
    region are left vanilla.
    """
    map_to_regions = _build_map_to_regions()

    # (sphere, map_name, source) keys -> deterministic order. PokemonSource is a StrEnum, so it
    # sorts as a string and indexes the encounters dict directly.
    scaled: list[tuple[int, str, PokemonSource]] = []
    for map_name, map_data in world.modified_maps.items():
        if not map_data.encounters:
            continue
        region = _representative_region(map_to_regions, map_name)
        if region is None:
            continue
        sphere = region_sphere.get(region)
        if sphere is None:
            continue  # map never reached -> leave its tables vanilla
        for source in map_data.encounters:
            scaled.append((sphere, map_name, source))

    if not scaled:
        return

    scaled.sort()
    targets = _generate_curve_levels(len(scaled), min_level, max_level, curve)

    for (_sphere, map_name, source), target in zip(scaled, targets):
        encounters = world.modified_maps[map_name].encounters
        encounters[source] = encounters[source]._replace(scaled_level=target)


def _scale_legendary_encounters(world: "PokemonEmeraldWorld",
                                min_level: int, max_level: int, curve: int) -> None:
    """
    Legendaries carry no region link, only an address, so rank them by their vanilla level as a
    progression proxy and assign the curve by rank. Each gets a single scaled level written by
    rom.py at address + 2.
    """
    # (vanilla_level, idx) -> deterministic order.
    scaled: list[tuple[int, int]] = []
    for idx, encounter in enumerate(world.modified_legendary_encounters):
        if encounter.level is None:
            continue
        scaled.append((encounter.level, idx))

    if not scaled:
        return

    scaled.sort()
    targets = _generate_curve_levels(len(scaled), min_level, max_level, curve)

    for (_vanilla_level, idx), target in zip(scaled, targets):
        encounter = world.modified_legendary_encounters[idx]
        world.modified_legendary_encounters[idx] = encounter._replace(scaled_level=target)
