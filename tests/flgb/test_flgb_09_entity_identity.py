import unittest
from skeleton.game.entity_identity import EntityIdentity

class TestEntityIdentity(unittest.TestCase):
    def test_generation_advances_without_changing_logical_identity(self):
        entity=EntityIdentity("p","w","e",0)
        nxt=entity.next_generation()
        self.assertEqual((nxt.project_id,nxt.world_id,nxt.entity_id),("p","w","e"))
        self.assertEqual(nxt.generation,1)
        self.assertNotEqual(nxt.digest,entity.digest)

if __name__=="__main__": unittest.main()
