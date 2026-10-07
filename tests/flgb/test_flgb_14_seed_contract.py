import unittest
from skeleton.game.generation.seed_contract import SeedContract
class T(unittest.TestCase):
 def test_derivation_is_deterministic(self):
  a=SeedContract("world",42,"v1"); self.assertEqual(a.derive("terrain").digest,a.derive("terrain").digest); self.assertNotEqual(a.digest,a.derive("terrain").digest)
if __name__=="__main__": unittest.main()
