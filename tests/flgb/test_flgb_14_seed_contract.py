import unittest
from skeleton.game.generation.seed_contract import GenerationContractError, SeedContract
D="a"*64
class TestSeedContract(unittest.TestCase):
    def test_derivation_is_deterministic_and_parent_bound(self):
        root=SeedContract("p","world","v1",42,D)
        a=root.derive("terrain")
        b=root.derive("terrain")
        c=root.derive("quests")
        self.assertEqual(a,b)
        self.assertEqual(a.parent_seed_digest,root.digest)
        self.assertNotEqual(a.seed,c.seed)
        with self.assertRaises(GenerationContractError):
            SeedContract("p","world","v1",-1,D)
if __name__=="__main__": unittest.main()
