from BaseClasses import ItemClassification

from . import PokemonEmeraldTestBase


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
