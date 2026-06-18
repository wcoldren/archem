from typing import NamedTuple
from unittest import TestCase

from ..data import data, RegionData, PokemonSource
from ..options import LevelScalingCurve
from ..scaling import _generate_curve_levels, _pin_superboss_trainers, _table_sphere, _target_levels


class TestTableSphere(TestCase):
    """
    Pin the wild-encounter scaling fix: a table is scaled by the earliest sphere among the regions
    that actually carry that encounter type, not by an arbitrary representative region. Models the
    Route-103 shape (early grass on WEST, Surf-gated fishing/water on EAST/WATER) that regressed to
    level-52-in-sphere-1 when the table keyed off the lexicographically-first (grass-less) region.
    """
    _FAKE = {
        "R/WEST": RegionData("R/WEST", None, has_grass=True, has_water=False, has_fishing=True),
        "R/EAST": RegionData("R/EAST", None, has_grass=False, has_water=False, has_fishing=True),
        "R/WATER": RegionData("R/WATER", None, has_grass=False, has_water=True, has_fishing=True),
    }
    _MAP_REGIONS = ["R/EAST", "R/WATER", "R/WEST"]  # not sorted; order must not matter
    _SPHERES = {"R/WEST": 1, "R/EAST": 8, "R/WATER": 8}

    _SENTINEL = object()

    def setUp(self) -> None:
        self._saved = {name: data.regions.get(name, self._SENTINEL) for name in self._FAKE}
        data.regions.update(self._FAKE)

    def tearDown(self) -> None:
        for name, prev in self._saved.items():
            if prev is self._SENTINEL:
                data.regions.pop(name, None)
            else:
                data.regions[name] = prev

    def test_land_keys_off_grass_region_not_first_sorted(self) -> None:
        # The core regression: LAND must follow the grass region (sphere 1), not the
        # lexicographically-first EAST (sphere 8, no grass).
        self.assertEqual(_table_sphere(self._SPHERES, self._MAP_REGIONS, PokemonSource.LAND), 1)

    def test_water_keys_off_water_region(self) -> None:
        self.assertEqual(_table_sphere(self._SPHERES, self._MAP_REGIONS, PokemonSource.WATER), 8)

    def test_fishing_takes_earliest_fishing_region(self) -> None:
        # All three regions have fishing; the earliest is WEST @ 1.
        self.assertEqual(_table_sphere(self._SPHERES, self._MAP_REGIONS, PokemonSource.FISHING), 1)

    def test_rock_smash_maps_to_grass_flag(self) -> None:
        self.assertEqual(_table_sphere(self._SPHERES, self._MAP_REGIONS, PokemonSource.ROCK_SMASH), 1)

    def test_fallback_to_any_region_when_no_type_match(self) -> None:
        # A map with only a water region, asked for LAND -> no grass region, so fall back to the
        # min sphere over all the map's regions.
        regions = ["R/WATER"]
        self.assertEqual(_table_sphere({"R/WATER": 5}, regions, PokemonSource.LAND), 5)

    def test_none_when_no_region_reachable(self) -> None:
        # No region has a computed sphere -> table left vanilla.
        self.assertIsNone(_table_sphere({}, self._MAP_REGIONS, PokemonSource.LAND))

    def test_empty_region_list(self) -> None:
        self.assertIsNone(_table_sphere(self._SPHERES, [], PokemonSource.LAND))


class TestCurveLevels(TestCase):
    """Pure curve math (ported from Crystal's _generate_curve_levels)."""

    def test_empty(self) -> None:
        self.assertEqual(_generate_curve_levels(0, 10, 50, LevelScalingCurve.option_linear), [])

    def test_single_is_min(self) -> None:
        self.assertEqual(_generate_curve_levels(1, 10, 50, LevelScalingCurve.option_linear), [10])

    def test_linear_even_spread(self) -> None:
        self.assertEqual(
            _generate_curve_levels(5, 10, 50, LevelScalingCurve.option_linear),
            [10, 20, 30, 40, 50],
        )

    def test_all_curves_monotonic_and_span_endpoints(self) -> None:
        for shape in (
            LevelScalingCurve.option_linear,
            LevelScalingCurve.option_sqrt,
            LevelScalingCurve.option_quadratic,
            LevelScalingCurve.option_s_curve,
        ):
            with self.subTest(shape=shape):
                levels = _generate_curve_levels(12, 5, 65, shape)
                self.assertEqual(levels[0], 5)
                self.assertEqual(levels[-1], 65)
                self.assertEqual(levels, sorted(levels))  # non-decreasing


# Minimal stubs mirroring just the attributes _pin_superboss_trainers touches.
class _Mon(NamedTuple):
    level: int


class _Party(NamedTuple):
    pokemon: list


class _Trainer:
    def __init__(self, party: _Party) -> None:
        self.party = party


class _World:
    def __init__(self, trainers: list) -> None:
        self.modified_trainers = trainers


class TestSuperbossPin(TestCase):
    """The superboss roof: weakest party member lands on max_level, the rest sit at/above it."""
    _SENTINEL = object()

    def setUp(self) -> None:
        # Point the pinned constant at index 0 of our stub trainer list, restore after.
        self._saved = data.constants.get("TRAINER_STEVEN", self._SENTINEL)
        data.constants["TRAINER_STEVEN"] = 0

    def tearDown(self) -> None:
        if self._saved is self._SENTINEL:
            data.constants.pop("TRAINER_STEVEN", None)
        else:
            data.constants["TRAINER_STEVEN"] = self._saved

    def test_weakest_on_max_rest_above(self) -> None:
        world = _World([_Trainer(_Party([_Mon(70), _Mon(75), _Mon(78)]))])
        _pin_superboss_trainers(world, max_level=65)
        levels = [m.level for m in world.modified_trainers[0].party.pokemon]
        self.assertEqual(min(levels), 65)               # weakest pinned exactly to the cap
        self.assertTrue(all(l >= 65 for l in levels))   # nothing below the cap
        self.assertGreater(levels[-1], 65)              # the ace sits above it
        self.assertEqual(levels, sorted(levels))        # spread/order preserved

    def test_clamps_to_100(self) -> None:
        world = _World([_Trainer(_Party([_Mon(10), _Mon(100)]))])
        _pin_superboss_trainers(world, max_level=95)
        levels = [m.level for m in world.modified_trainers[0].party.pokemon]
        self.assertEqual(min(levels), 95)
        self.assertLessEqual(max(levels), 100)

    def test_empty_party_is_noop(self) -> None:
        world = _World([_Trainer(_Party([]))])
        _pin_superboss_trainers(world, max_level=65)
        self.assertEqual(world.modified_trainers[0].party.pokemon, [])


class TestWildStaticCap(TestCase):
    """The 2/3-of-trainer-max cap applied to wild + legendary curves (Crystal's wild_static_max)."""

    def test_two_thirds_and_floor_clamp(self) -> None:
        cases = [
            (2, 65, 43),   # round(65*2/3) = 43
            (2, 73, 49),   # round(73*2/3) = 49 (Crystal's default max)
            (50, 60, 50),  # 2/3 dips below min -> clamps to min_level
        ]
        for min_level, max_level, expected in cases:
            with self.subTest(min_level=min_level, max_level=max_level):
                self.assertEqual(max(min_level, round(max_level * 2 / 3)), expected)


class TestTargetLevels(TestCase):
    """The rung selector: vanilla reuses the real levels (sorted, min/max ignored); others curve."""

    def test_vanilla_returns_sorted_vanilla(self) -> None:
        vanilla = [40, 5, 22, 5, 60]
        self.assertEqual(
            _target_levels(LevelScalingCurve.option_vanilla, vanilla, min_level=2, max_level=65),
            sorted(vanilla),
        )

    def test_vanilla_ignores_min_max(self) -> None:
        # Vanilla values pass straight through even when they sit outside [min, max].
        self.assertEqual(
            _target_levels(LevelScalingCurve.option_vanilla, [80, 10], min_level=2, max_level=65),
            [10, 80],
        )

    def test_non_vanilla_matches_curve(self) -> None:
        # The vanilla_levels values are unused for synthetic curves; only their count matters.
        out = _target_levels(LevelScalingCurve.option_linear, [0, 0, 0, 0, 0], min_level=10, max_level=50)
        self.assertEqual(out, _generate_curve_levels(5, 10, 50, LevelScalingCurve.option_linear))
        self.assertEqual(out, [10, 20, 30, 40, 50])


class TestVanillaLevelDataLoaded(TestCase):
    """The extraction enabler: wild_levels.json / misc_levels.json are joined onto the data model."""

    def test_wild_levels_aligned_with_slots(self) -> None:
        carried = 0
        for map_data in data.maps.values():
            for table in map_data.encounters.values():
                if table.min_levels is not None:
                    carried += 1
                    self.assertEqual(len(table.min_levels), len(table.slots))
                    self.assertEqual(len(table.max_levels), len(table.slots))
        self.assertGreater(carried, 0, "expected wild tables to carry backfilled vanilla levels")

    def test_misc_levels_populated_with_eggs_absent(self) -> None:
        levels = [mon.level for mon in data.misc_pokemon]
        self.assertTrue(any(level is not None for level in levels),
                        "expected some misc Pokemon to carry a backfilled vanilla level")
        # Level-less entries are expected (e.g. the Wynaut egg gift, which has no decomp level).
        self.assertTrue(any(level is None for level in levels))
