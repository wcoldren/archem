from BaseClasses import ItemClassification

from . import PokemonEmeraldTestBase
from ..data import data


class TestNoTrapsByDefault(PokemonEmeraldTestBase):
    options = {
        "filler_trap_percentage": 0,
    }

    def test_no_traps_in_pool(self) -> None:
        traps = [item for item in self.multiworld.itempool
                 if item.player == 1 and item.classification & ItemClassification.trap]
        self.assertEqual(len(traps), 0)


class TestTrapsBlendedIntoFiller(PokemonEmeraldTestBase):
    options = {
        "filler_trap_percentage": 100,
    }

    def test_filler_replaced_with_traps(self) -> None:
        # With 100% filler trap percentage, every replaceable filler item should become a trap.
        own_items = [item for item in self.multiworld.itempool if item.player == 1]
        traps = [item for item in own_items if item.classification & ItemClassification.trap]
        self.assertGreater(len(traps), 0, "no traps were placed at 100%")
        for trap in traps:
            self.assertIn("Trap", trap.tags)
        # No pure-filler items should remain (all eligible filler converted to traps).
        remaining_filler = [item for item in own_items
                            if item.classification == ItemClassification.filler and "Unique" not in item.tags]
        self.assertEqual(len(remaining_filler), 0, "filler items remained at 100% trap percentage")


class TestTrapLocationsLocalDelivery(PokemonEmeraldTestBase):
    options = {
        "filler_trap_percentage": 100,
        "remote_items": "false",
    }

    def test_trap_locations_populated_when_local(self) -> None:
        # With local items, the client needs flag_id -> trap label to apply traps itself.
        # WorldTestBase.setUp doesn't fill, so place items before reading the placement-derived map.
        from Fill import distribute_items_restrictive
        distribute_items_restrictive(self.multiworld)
        slot_data = self.world.fill_slot_data()
        self.assertIn("trap_locations", slot_data)
        trap_locations = slot_data["trap_locations"]
        self.assertGreater(len(trap_locations), 0, "no local trap locations exported")
        for name in trap_locations.values():
            self.assertIn("Trap", self.world.create_item(name).tags)


class TestTrapLocationsRemoteDelivery(PokemonEmeraldTestBase):
    options = {
        "filler_trap_percentage": 100,
        "remote_items": "true",
    }

    def test_trap_locations_omitted_when_remote(self) -> None:
        # Remote items arrive via handle_received_items; exporting trap_locations would double-fire.
        slot_data = self.world.fill_slot_data()
        self.assertNotIn("trap_locations", slot_data)


class TestTrapItemRoster(PokemonEmeraldTestBase):
    options = {
        "filler_trap_percentage": 0,
    }

    def test_poison_and_sleep_traps_registered(self) -> None:
        by_label = {item.label: item for item in data.items.values()}
        for label in ("Poison Trap", "Sleep Trap"):
            self.assertIn(label, by_label, f"{label} missing from item data")
            self.assertTrue(by_label[label].classification & ItemClassification.trap)
            self.assertIn("Trap", by_label[label].tags)


class TestTrapMagnitudeDefaults(PokemonEmeraldTestBase):
    options = {}

    def test_default_party_portions_in_slot_data(self) -> None:
        slot_data = self.world.fill_slot_data()
        self.assertEqual(slot_data["poison_trap_party_portion"], 1)
        self.assertEqual(slot_data["sleep_trap_party_portion"], 1)


class TestTrapMagnitudeNamedValues(PokemonEmeraldTestBase):
    options = {
        "poison_trap_party_portion": "all",
        "sleep_trap_party_portion": "half",
    }

    def test_named_party_portions_resolve(self) -> None:
        slot_data = self.world.fill_slot_data()
        self.assertEqual(slot_data["poison_trap_party_portion"], 100)
        self.assertEqual(slot_data["sleep_trap_party_portion"], 50)


class TestSingleTrapTypeWeighting(PokemonEmeraldTestBase):
    options = {
        "filler_trap_percentage": 100,
        "trap_weights": {"Faint Trap": 0, "Poison Trap": 1, "Sleep Trap": 0},
    }

    def test_only_weighted_trap_is_placed(self) -> None:
        from Fill import distribute_items_restrictive
        distribute_items_restrictive(self.multiworld)
        placed_traps = [
            loc.item for loc in self.multiworld.get_locations(self.player)
            if loc.item is not None and loc.item.player == self.player
            and (loc.item.classification & ItemClassification.trap)
        ]
        self.assertGreater(len(placed_traps), 0, "no traps placed at 100%")
        for trap in placed_traps:
            self.assertEqual(trap.name, "Poison Trap")
