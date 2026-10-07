import unittest
from skeleton.game.world_identity import WorldIdentity
D="a"*64
class TestWorldIdentity(unittest.TestCase):
    def test_generation_participates_in_identity(self):
        a=WorldIdentity("w","p",0,D)
        b=WorldIdentity("w","p",1,D)
        self.assertNotEqual(a.digest,b.digest)
if __name__=="__main__": unittest.main()
