"""
Sphere-based trainer level scaling for Pokemon Emerald (v1: trainers only).

Called from PokemonEmeraldWorld.generate_output(), AFTER randomize_opponent_parties()
(so party levels exist) and BEFORE write_tokens() builds the patch.

Approach (adapted from the Pokemon Crystal Archipelago level-scaling implementation by
cheerioschelsea — PR #127 "Implement Sphere Based Level Scaling" — and James White):
all scaled trainers are ordered by logical progression depth (the sphere in which their
region first becomes reachable, then by vanilla party strength), and a curve of target
levels from the configured min to max is distributed across them by rank. Each trainer's
party is then rescaled to its target while preserving the party's internal level spread.

Trainers without a TRAINER reward location have no region data and are left at vanilla
levels (this covers rematches and Battle Frontier brains, matching Crystal's default of
excluding rematches). The trainer->region map is the only coverage gate, so fuller
coverage can be added later without touching the curve/assignment logic.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from BaseClasses import CollectionState

from .data import data, LocationCategory
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
        map_to_regions: dict[str, list[str]] = {}
        for region_name, region_data in data.regions.items():
            parent_map = getattr(region_data, "parent_map", None)
            if parent_map is not None:
                map_to_regions.setdefault(parent_map.name, []).append(region_name)

        def _representative_region(map_id: str) -> "str | None":
            # Sub-region sphere differences within one map are 0-1, so a representative region
            # suffices: prefer the map's main region, else the lexicographically-first region.
            regions = sorted(map_to_regions.get(map_id, []))
            if not regions:
                return None  # map has no AP region (cut/unused) -> leave trainer vanilla
            for region in regions:
                if region.endswith("/MAIN"):
                    return region
            return regions[0]

        for trainer_const, entry in data.trainer_map.items():
            if entry.get("rematch"):  # excluded by default; future opt-in flips this guard
                continue
            idx = data.constants.get(trainer_const)
            if idx is None or idx in trainer_region:
                continue
            region = _representative_region(entry["map"])
            if region is not None:
                trainer_region[idx] = region

    return trainer_region


def perform_level_scaling(world: "PokemonEmeraldWorld") -> None:
    region_sphere = _compute_region_spheres(world)
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
    targets = _generate_curve_levels(
        len(scaled),
        world.options.level_scaling_min_level.value,
        world.options.level_scaling_max_level.value,
        world.options.level_scaling_curve.value,
    )

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
