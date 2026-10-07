import unittest
from skeleton.game.project_manifest import ProjectManifest
D="a"*64
class TestProjectManifest(unittest.TestCase):
    def test_manifest_identity_is_deterministic(self):
        a=ProjectManifest("p",1,("w2","w1"),D,D)
        b=ProjectManifest("p",1,("w1","w2"),D,D)
        self.assertEqual(a.world_ids,("w1","w2"))
        self.assertEqual(a.digest,b.digest)
if __name__=="__main__": unittest.main()
