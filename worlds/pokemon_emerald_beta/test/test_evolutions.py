from . import PokemonEmeraldTestBase
from ..data import data


class TestEvolutionsVanilla(PokemonEmeraldTestBase):
    options = {
        "evolutions": "vanilla",
    }

    def test_evolutions_unchanged(self) -> None:
        world = self.multiworld.worlds[1]
        for species_id, species in world.modified_species.items():
            self.assertEqual(species.evolutions, data.species[species_id].evolutions)


class TestEvolutionsRandom(PokemonEmeraldTestBase):
    options = {
        "evolutions": "completely_random",
    }

    def test_structure_preserved_targets_valid(self) -> None:
        world = self.multiworld.worlds[1]
        valid_ids = set(world.modified_species.keys())
        for species_id, species in world.modified_species.items():
            vanilla = data.species[species_id].evolutions
            # Same number of evolutions, methods/params preserved, only targets change.
            self.assertEqual(len(species.evolutions), len(vanilla))
            for new_evo, old_evo in zip(species.evolutions, vanilla):
                self.assertEqual(new_evo.method, old_evo.method)
                self.assertEqual(new_evo.param, old_evo.param)
                self.assertIn(new_evo.species_id, valid_ids)
                self.assertNotEqual(new_evo.species_id, species_id, "evolution points at itself")


class TestEvolutionsRandomSimilarBst(PokemonEmeraldTestBase):
    options = {
        "evolutions": "match_base_stats",
    }

    def test_targets_have_similar_bst(self) -> None:
        world = self.multiworld.worlds[1]
        for species_id, species in world.modified_species.items():
            vanilla = data.species[species_id].evolutions
            for new_evo, old_evo in zip(species.evolutions, vanilla):
                original_bst = sum(data.species[old_evo.species_id].base_stats)
                new_bst = sum(data.species[new_evo.species_id].base_stats)
                # filter_species_by_nearby_bst keeps candidates within ~10% (with a minimum window).
                self.assertLessEqual(abs(new_bst - original_bst), max(original_bst * 0.5, 100),
                                     f"BST too far for {species.name}")
