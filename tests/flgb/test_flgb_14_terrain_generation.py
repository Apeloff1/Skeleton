import unittest
from skeleton.game.generation.seed_contract import SeedContract
from skeleton.game.generation.terrain_generation import generate_terrain_tile
D="a"*64
E="b"*64
class TestTerrainGeneration(unittest.TestCase):
    def test_tile_hash_is_seed_coordinate_and_resolution_bound(self):
        seed=SeedContract("p","terrain","v1",7,D)
        a=generate_terrain_tile(seed,1,2,256,E)
        b=generate_terrain_tile(seed,1,2,256,E)
        c=generate_terrain_tile(seed,2,2,256,E)
        self.assertEqual(a,b)
        self.assertNotEqual(a.height_digest,c.height_digest)
if __name__=="__main__": unittest.main()
