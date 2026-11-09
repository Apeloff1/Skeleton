import unittest
from skeleton.game.generation.regeneration_diff import ContinuityContractError, GeneratedArtifact, regeneration_diff
D="a"*64
E="b"*64

class TestRegenerationDiff(unittest.TestCase):
    def test_locked_artifacts_cannot_change_or_disappear(self):
        before=(GeneratedArtifact("locked",D,True),GeneratedArtifact("mutable",D,False))
        after=(GeneratedArtifact("locked",D,True),GeneratedArtifact("mutable",E,False),GeneratedArtifact("new",E,False))
        diff=regeneration_diff(before,after)
        self.assertEqual(diff.changed,("mutable",))
        self.assertEqual(diff.added,("new",))
        self.assertEqual(diff.preserved_locked,("locked",))
        with self.assertRaises(ContinuityContractError):
            regeneration_diff(before,(GeneratedArtifact("locked",E,True),))

if __name__=="__main__": unittest.main()
