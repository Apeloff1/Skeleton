import unittest
from skeleton.game.presentation.animation_graph import AnimationGraph, AnimationNode, PresentationContractError
D="a"*64
class TestAnimationGraph(unittest.TestCase):
    def test_cycle_rejected(self):
        g=AnimationGraph((AnimationNode("idle","clip",(),D),AnimationNode("out","blend",("idle",),D)),"out")
        self.assertEqual(len(g.digest),64)
        with self.assertRaises(PresentationContractError):
            AnimationGraph((AnimationNode("a","x",("b",),D),AnimationNode("b","x",("a",),D)),"a")
if __name__=="__main__": unittest.main()
