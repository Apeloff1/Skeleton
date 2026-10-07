import unittest
from skeleton.ai.assurance.golden_fixtures import GoldenFixture
D="a"*64
E="b"*64

class TestGoldenFixtures(unittest.TestCase):
    def test_revision_binds_parent_and_input(self):
        base=GoldenFixture("f",0,D,D,E)
        nxt=base.revise(E,D)
        self.assertEqual(nxt.version,1)
        self.assertEqual(nxt.parent_digest,base.digest)
        self.assertEqual(nxt.input_digest,base.input_digest)

if __name__=="__main__": unittest.main()
