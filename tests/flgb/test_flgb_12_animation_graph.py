import unittest
from skeleton.game.presentation.animation_graph import AnimationGraph, AnimationState, AnimationTransition, PresentationContractError
D="a"*64
class TestAnimationGraph(unittest.TestCase):
    def test_event_transition_is_unambiguous(self):
        states=(AnimationState("idle",D,True),AnimationState("run",D,True))
        graph=AnimationGraph(states,(AnimationTransition("idle","move","run",100),),"idle")
        self.assertEqual(graph.transition("idle","move"),"run")
        with self.assertRaises(PresentationContractError):
            AnimationGraph(states,(AnimationTransition("idle","move","run",0),AnimationTransition("idle","move","idle",0)),"idle")
if __name__=="__main__":unittest.main()
