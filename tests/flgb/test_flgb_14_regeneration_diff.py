import unittest
from skeleton.game.generation.regeneration_diff import GenerationContractError, RegenerationDiff
D="a"*64
E="b"*64
class TestRegenerationDiff(unittest.TestCase):
    def test_diff_categories_are_disjoint(self):
        diff=RegenerationDiff("zone",D,E,("new",),("old",),("changed",),D)
        self.assertTrue(diff.changed)
        with self.assertRaises(GenerationContractError):
            RegenerationDiff("zone",D,E,("same",),(),("same",),D)
if __name__=="__main__": unittest.main()
