import unittest
from skeleton.game.project_manifest import GameProjectError, ProjectManifest
D="a"*64
E="b"*64

class TestProjectManifest(unittest.TestCase):
    def test_revision_chain_is_durable(self):
        base=ProjectManifest("p",0,1,("w",),D,D,D)
        nxt=base.revise(config_digest=E)
        self.assertEqual(nxt.revision,1)
        self.assertEqual(nxt.parent_manifest_digest,base.digest)
        with self.assertRaises(GameProjectError):
            ProjectManifest("p",1,1,("w",),D,D,D)

if __name__=="__main__": unittest.main()
