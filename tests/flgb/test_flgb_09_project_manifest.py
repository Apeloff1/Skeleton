import unittest
from skeleton.game.project_manifest import GameContractError, ProjectManifest
D="a"*64

class TestProjectManifest(unittest.TestCase):
    def test_world_ids_are_unique_and_canonical(self):
        manifest=ProjectManifest("p",1,D,("world-b","world-a"),D,D,D)
        self.assertEqual(manifest.world_ids,("world-a","world-b"))
        self.assertEqual(len(manifest.digest),64)
        with self.assertRaises(GameContractError):
            ProjectManifest("p",1,D,("world-a","world-a"),D,D,D)

if __name__=="__main__": unittest.main()
