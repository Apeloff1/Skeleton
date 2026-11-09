import unittest
from skeleton.game.presentation.animation_graph import AnimationGraph, AnimationState, AnimationTransition
D="a"*64

class TestAnimationGraph(unittest.TestCase):
    def test_highest_priority_satisfied_transition_wins(self):
        states=(AnimationState("idle",D,True),AnimationState("walk",D,True),AnimationState("run",D,True))
        transitions=(AnimationTransition("walk","idle","walk",D,1,100),AnimationTransition("run","idle","run",D,2,50))
        graph=AnimationGraph(states,transitions,"idle")
        self.assertEqual(graph.resolve("idle",("walk","run")),"run")
        self.assertEqual(graph.resolve("idle",()),"idle")

if __name__=="__main__": unittest.main()
