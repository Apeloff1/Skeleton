import unittest
from skeleton.game.world_identity import WorldIdentity

class TestWorldIdentity(unittest.TestCase):
    def test_identity_is_project_scoped(self):
        a=WorldIdentity("p1","w","world",0)
        b=WorldIdentity("p2","w","world",0)
        self.assertNotEqual(a.digest,b.digest)

if __name__=="__main__": unittest.main()
