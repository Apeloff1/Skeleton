import unittest
from skeleton.game.scene_graph import GameContractError, SceneGraph, SceneNode
D="a"*64

class TestSceneGraph(unittest.TestCase):
    def test_parent_precedes_child_and_cycles_fail(self):
        graph=SceneGraph((SceneNode("child","root",D,D,2),SceneNode("root",None,D,D,1)))
        self.assertEqual(graph.topological_entities,("root","child"))
        with self.assertRaises(GameContractError):
            SceneGraph((SceneNode("a","b",D,D,1),SceneNode("b","a",D,D,2)))

if __name__=="__main__": unittest.main()
