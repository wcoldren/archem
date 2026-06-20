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


class TestOwnTrapNaming(PokemonEmeraldTestBase):
    # remote_items off -> own traps are local pickups whose pickup box is driven by
    # gArchipelagoNameTable. The engine's message routine (RE: games/emerald/re/NAMING.md,
    # ROM 0x0809CB4C) suppresses the box for any entry with player-name id 0, so own traps
    # must be written with a NON-ZERO id pointing at the local player's own name. This guards
    # rom.py from regressing to the id-0 (blank box) behaviour.
    options = {
        "filler_trap_percentage": 100,
        "remote_items": "false",
    }

    def test_own_traps_use_nonzero_player_name_id(self) -> None:
        from Fill import distribute_items_restrictive
        from ..data import data
        from ..rom import write_tokens

        distribute_items_restrictive(self.multiworld)

        writes: "list[tuple[int, bytes]]" = []

        class _CapturePatch:
            def write_token(self, _token_type, address, data_bytes):
                writes.append((address, data_bytes))

        # The gArchipelagoNameTable block runs near the top of write_tokens, before the later
        # _set_* sections that need generate_output-stage state (modified_misc_pokemon, etc.) we
        # don't set up here. So the name-table writes are fully captured before any such
        # AttributeError; tolerate it and assert on what was captured. (If the block ever stopped
        # running, the assertions below would fail loudly — no silent pass.)
        try:
            write_tokens(self.world, _CapturePatch())
        except AttributeError:
            pass

        nt_base = data.rom_addresses["gArchipelagoNameTable"]
        item_off: "dict[int, int]" = {}
        pid: "dict[int, int]" = {}
        for address, data_bytes in writes:
            rel = address - nt_base
            if rel < 0 or rel >= 5 * 2000:
                continue
            entry, field = divmod(rel, 5)
            if field == 2:
                item_off[entry] = int.from_bytes(data_bytes[:2], "little")
            elif field == 4:
                pid[entry] = data_bytes[0]

        # Single player + remote_items off: every non-zero-id entry is a named own trap.
        named_own = [e for e, p in pid.items() if p != 0]
        self.assertGreater(len(named_own), 0,
                           "own traps must get a non-zero player-name id, else the engine "
                           "suppresses the pickup box (blank name)")
        # No entry should carry a real item name while still suppressed at id 0 (the old bug).
        named_but_suppressed = [e for e, off in item_off.items() if off != 0 and pid.get(e, 0) == 0]
        self.assertEqual(named_but_suppressed, [],
                         "name-table entries with an item name must use a non-zero player-name id")
