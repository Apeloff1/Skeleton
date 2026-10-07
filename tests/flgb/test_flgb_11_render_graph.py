import unittest
from skeleton.game.render.render_graph import RenderContractError, RenderGraph, RenderPass

class TestRenderGraph(unittest.TestCase):
    def test_render_dependencies_form_dag(self):
        graph=RenderGraph((RenderPass("g",(),(),("gbuf",)),RenderPass("l",("g",),("gbuf",),("lit",))))
        self.assertEqual(graph.waves,(("g",),("l",)))
        with self.assertRaises(RenderContractError):
            RenderGraph((RenderPass("a",("b",),(),("x",)),RenderPass("b",("a",),(),("y",))))

if __name__=="__main__": unittest.main()
