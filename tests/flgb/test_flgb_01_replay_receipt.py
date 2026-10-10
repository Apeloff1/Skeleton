import unittest
from skeleton.inference.replay_receipt import ReplayReceipt
D = "a" * 64
E = "b" * 64
class TestReplayReceipt(unittest.TestCase):
    def test_binds_authoritative_digests(self):
        receipt = ReplayReceipt("op", D, D, E, E)
        self.assertTrue(receipt.verifies(request_digest=D, event_chain_digest=D, result_digest=E, terminal_commit_digest=E))
        self.assertFalse(receipt.verifies(request_digest=D, event_chain_digest=E, result_digest=E, terminal_commit_digest=E))
if __name__ == "__main__": unittest.main()
