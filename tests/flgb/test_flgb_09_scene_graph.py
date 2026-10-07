import unittest
from skeleton.game.scene_graph import CreatorContractError, SceneGraph, SceneNode
D="a"*64
class TestSceneGraph(unittest.TestCase):
    def test_parent_order_and_cycle_detection(self):
        graph=SceneGraph((SceneNode("child","root","e",D),SceneNode("root",None,None,D)))
        self.assertEqual(graph.order,("root","child"))
        with self.assertRaises(CreatorContractError):
            SceneGraph((SceneNode("a","b",None,D),SceneNode("b","a",None,D)))
if __name__=="__main__": unittest.main()
