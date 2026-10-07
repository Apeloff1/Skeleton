import unittest
from skeleton.inference.conversation_state import ConversationState, FLGBInferenceError
class TestConversationState(unittest.TestCase):
    def test_revision_and_immutability(self):
        base = ConversationState("c")
        one = base.append("user", "hello")
        two = one.append("assistant", "hi")
        self.assertEqual((base.revision, one.revision, two.revision), (0, 1, 2))
        with self.assertRaises(FLGBInferenceError):
            ConversationState("c", revision=2, turns=one.turns)
if __name__ == "__main__": unittest.main()
