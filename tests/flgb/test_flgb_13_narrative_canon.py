import unittest
from skeleton.game.gameplay.narrative_canon import CanonFact
D="a"*64
E="b"*64
class TestCanon(unittest.TestCase):
    def test_revision_binds_parent(self):
        fact=CanonFact("f",D,E)
        revised=fact.revise(E,D)
        self.assertEqual(revised.revision,1)
        self.assertEqual(revised.parent_digest,fact.digest)
if __name__=="__main__": unittest.main()
