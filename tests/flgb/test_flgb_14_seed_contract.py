import unittest
from skeleton.game.generation.seed_contract import SeedContract
D="a"*64

class TestSeedContract(unittest.TestCase):
    def test_domain_derivation_is_stable_and_separated(self):
        seed=SeedContract("p",D,"v1")
        self.assertEqual(seed.derive("terrain","0,0"),seed.derive("terrain","0,0"))
        self.assertNotEqual(seed.derive("terrain","0,0"),seed.derive("quest","0,0"))

if __name__=="__main__": unittest.main()
