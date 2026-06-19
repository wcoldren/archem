from . import PokemonEmeraldTestBase


class TestBaseStatsVanilla(PokemonEmeraldTestBase):
    options = {
        "base_stats": "vanilla",
    }

    def test_stats_unchanged(self) -> None:
        from ..data import data
        world = self.multiworld.worlds[1]
        for species_id, species in world.modified_species.items():
            self.assertEqual(tuple(species.base_stats), tuple(data.species[species_id].base_stats))


class TestBaseStatsShuffle(PokemonEmeraldTestBase):
    options = {
        "base_stats": "shuffle",
    }

    def test_bst_preserved_and_in_range(self) -> None:
        from ..data import data
        world = self.multiworld.worlds[1]
        for species_id, species in world.modified_species.items():
            vanilla = data.species[species_id].base_stats
            self.assertEqual(sum(species.base_stats), sum(vanilla), f"BST changed for {species.name}")
            self.assertEqual(sorted(species.base_stats), sorted(vanilla), f"stats not a permutation for {species.name}")
            for stat in species.base_stats:
                self.assertTrue(0 <= stat <= 255)


class TestBaseStatsRandomKeepBst(PokemonEmeraldTestBase):
    options = {
        "base_stats": "random_keep_bst",
    }

    def test_bst_preserved_within_byte_band(self) -> None:
        from ..data import data
        world = self.multiworld.worlds[1]
        for species_id, species in world.modified_species.items():
            vanilla_bst = sum(data.species[species_id].base_stats)
            # BST is preserved unless the original total can't fit the floor/ceiling band.
            min_total, max_total = 10 * 6, 255 * 6
            expected = min(max(vanilla_bst, min_total), max_total)
            self.assertEqual(sum(species.base_stats), expected, f"BST not preserved for {species.name}")
            for stat in species.base_stats:
                self.assertTrue(10 <= stat <= 255, f"stat out of band for {species.name}: {stat}")


class TestBaseStatsCompletelyRandom(PokemonEmeraldTestBase):
    options = {
        "base_stats": "completely_random",
    }

    def test_stats_in_band(self) -> None:
        world = self.multiworld.worlds[1]
        for species in world.modified_species.values():
            for stat in species.base_stats:
                self.assertTrue(10 <= stat <= 255, f"stat out of band for {species.name}: {stat}")
