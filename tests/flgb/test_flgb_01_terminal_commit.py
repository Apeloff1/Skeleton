import unittest
from skeleton.inference.terminal_commit import FLGBInferenceError, TerminalCommitReceipt
D = "a" * 64
E = "b" * 64
class TestTerminalCommit(unittest.TestCase):
    def test_failed_terminal_cannot_mutate_state(self):
        receipt = TerminalCommitReceipt("op", D, D, D, E, 0, "idem", "completed")
        self.assertEqual(len(receipt.digest), 64)
        with self.assertRaises(FLGBInferenceError):
            TerminalCommitReceipt("op", D, D, D, E, 0, "idem", "provider_error")
if __name__ == "__main__": unittest.main()
