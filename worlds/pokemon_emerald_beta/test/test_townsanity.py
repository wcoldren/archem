from . import PokemonEmeraldTestBase
from ..data import BASE_OFFSET, LocationCategory, data

# The 16 town/city FLAG_VISITED_* flags the engine sets on first arrival (see data.TOWN_FLAG_TO_REGION).
EXPECTED_TOWN_FLAGS = list(range(2159, 2175))


def _town_locations(multiworld):
    return [loc for loc in multiworld.get_locations(1)
            if loc.key is not None and data.locations[loc.key].category == LocationCategory.TOWN]


class TestNoTownsanityByDefault(PokemonEmeraldTestBase):
    options = {
        "townsanity": "false",
    }

    def test_no_town_locations(self) -> None:
        self.assertEqual(len(_town_locations(self.multiworld)), 0)


class TestTownsanityLocations(PokemonEmeraldTestBase):
    options = {
        "townsanity": "true",
        # Town rewards are delivered over the network (no in-game item slot).
        "remote_items": "true",
    }

    def test_sixteen_town_locations(self) -> None:
        towns = _town_locations(self.multiworld)
        self.assertEqual(len(towns), 16)

    def test_ids_match_flag_plus_base_offset(self) -> None:
        towns = _town_locations(self.multiworld)
        flags = sorted(data.locations[loc.key].flag for loc in towns)
        self.assertEqual(flags, EXPECTED_TOWN_FLAGS)
        for loc in towns:
            self.assertEqual(loc.address, data.locations[loc.key].flag + BASE_OFFSET)
            self.assertTrue(loc.name.endswith(" - Visited"))

    def test_town_regions_resolve(self) -> None:
        # Every town location lives in a real region (catches a typo'd TOWN_FLAG_TO_REGION entry,
        # incl. the two no-"/MAIN" special cases Sootopolis -> /WATER and Ever Grande -> /SEA).
        for loc in _town_locations(self.multiworld):
            self.assertIn(data.locations[loc.key].parent_region, data.regions)

    def test_pool_fills_every_town(self) -> None:
        # WorldTestBase.setUp constructs but does not fill, so distribute first. A reachable,
        # fillable item at each town also confirms the locations are in-logic (incl. the
        # special-case Sootopolis/Ever Grande arrival regions).
        from Fill import distribute_items_restrictive
        distribute_items_restrictive(self.multiworld)
        for loc in _town_locations(self.multiworld):
            self.assertIsNotNone(loc.item, f"no item placed at {loc.name}")
