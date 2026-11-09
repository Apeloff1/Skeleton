import unittest
from skeleton.game.render.render_graph import RenderContractError, RenderGraph, RenderPass

class TestRenderGraph(unittest.TestCase):
    def test_dependencies_are_acyclic_and_ordered(self):
        graph=RenderGraph((RenderPass("lighting",("gbuffer",),("lit",),("geometry",)),RenderPass("geometry",(),("gbuffer",))))
        self.assertEqual(graph.execution_order,("geometry","lighting"))
        with self.assertRaises(RenderContractError):
            RenderGraph((RenderPass("a",(),("ra",),("b",)),RenderPass("b",(),("rb",),("a",))))

if __name__=="__main__": unittest.main()
