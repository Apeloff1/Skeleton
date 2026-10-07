import unittest
from skeleton.game.entity_identity import EntityIdentity
class TestEntityIdentity(unittest.TestCase):
    def test_generation_advances_without_id_reuse(self):
        base=EntityIdentity("e","w")
        nxt=base.next_generation()
        self.assertEqual((nxt.entity_id,nxt.world_id,nxt.generation),("e","w",1))
        self.assertNotEqual(base.digest,nxt.digest)
if __name__=="__main__": unittest.main()
