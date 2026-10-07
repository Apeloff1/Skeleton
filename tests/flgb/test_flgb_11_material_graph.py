import unittest
from skeleton.game.render.material_graph import MaterialNode, RenderContractError, validate_material_graph

class TestMaterialGraph(unittest.TestCase):
    def test_output_reachable_graph_is_acyclic(self):
        nodes=(MaterialNode("tex","sample",(),"texture"),MaterialNode("out","shade",("tex",),"color"))
        self.assertEqual([n.node_id for n in validate_material_graph(nodes,"out")],["out","tex"])
        with self.assertRaises(RenderContractError):
            validate_material_graph((MaterialNode("a","x",("b",),"color"),MaterialNode("b","x",("a",),"color")),"a")

if __name__=="__main__": unittest.main()
