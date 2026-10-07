import unittest
from skeleton.game.gameplay.dialogue_graph import DialogueChoice, DialogueGraph, DialogueNode, GameplayContractError
D="a"*64
class TestDialogueGraph(unittest.TestCase):
    def test_choice_targets_must_exist(self):
        graph=DialogueGraph((DialogueNode("a",D,(DialogueChoice("next","b"),)),DialogueNode("b",D,())),"a")
        self.assertEqual(graph.entry_node,"a")
        with self.assertRaises(GameplayContractError):
            DialogueGraph((DialogueNode("a",D,(DialogueChoice("bad","missing"),)),),"a")
if __name__=="__main__": unittest.main()
