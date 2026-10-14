import unittest
from skeleton.game.render.material_graph import MaterialGraph, MaterialNode, RenderContractError
D="a"*64

class TestMaterialGraph(unittest.TestCase):
    def test_all_nodes_are_cycle_checked(self):
        graph=MaterialGraph((MaterialNode("base","constant",(),D),MaterialNode("out","multiply",("base",),D)),"out")
        self.assertEqual(len(graph.digest),64)
        with self.assertRaises(RenderContractError):
            MaterialGraph((MaterialNode("a","x",("b",),D),MaterialNode("b","x",("a",),D),MaterialNode("out","x",(),D)),"out")

if __name__=="__main__": unittest.main()
