import unittest
from skeleton.game.entity_identity import EntityIdentity

class TestEntityIdentity(unittest.TestCase):
    def test_entity_identity_binds_project_world_scene_and_generation(self):
        a=EntityIdentity("p","w","s","e",0)
        b=EntityIdentity("p","w","s","e",1)
        self.assertNotEqual(a.digest,b.digest)

if __name__=="__main__": unittest.main()
