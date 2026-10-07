import unittest
from skeleton.game.scene_graph import GameProjectError, SceneGraph, SceneNode

class TestSceneGraph(unittest.TestCase):
    def test_single_root_acyclic_graph_and_entity_custody(self):
        graph=SceneGraph((SceneNode("root",None,None,0),SceneNode("child","root","e",1)))
        self.assertEqual(graph.root_id,"root")
        with self.assertRaises(GameProjectError):
            SceneGraph((SceneNode("root",None,None,0),SceneNode("a","b",None,1),SceneNode("b","a",None,2)))
        with self.assertRaises(GameProjectError):
            SceneGraph((SceneNode("root",None,None,0),SceneNode("a","root","e",1),SceneNode("b","root","e",2)))

if __name__=="__main__": unittest.main()
