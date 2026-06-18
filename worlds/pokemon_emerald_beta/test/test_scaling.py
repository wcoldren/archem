from unittest import TestCase

from ..data import data, RegionData, PokemonSource
from ..options import LevelScalingCurve
from ..scaling import _generate_curve_levels, _table_sphere


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
