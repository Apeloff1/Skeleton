import unittest
from skeleton.game.world_identity import GameContractError, WorldIdentity
D="a"*64
E="b"*64

class TestWorldIdentity(unittest.TestCase):
    def test_revision_chain_binds_parent(self):
        base=WorldIdentity("p","w",0,D,D)
        nxt=base.revise(E)
        self.assertEqual(nxt.world_revision,1)
        self.assertEqual(nxt.parent_world_digest,base.digest)
        with self.assertRaises(GameContractError):
            WorldIdentity("p","w",1,D,E)

if __name__=="__main__": unittest.main()
