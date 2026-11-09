import unittest
from skeleton.inference.cancellation import CancellationToken, CancelledError
class TestCancellation(unittest.TestCase):
    def test_idempotent_fence(self):
        token = CancellationToken("op")
        self.assertTrue(token.cancel("operator"))
        self.assertFalse(token.cancel("late"))
        with self.assertRaises(CancelledError):
            token.raise_if_cancelled()
        self.assertEqual(len(token.receipt_digest), 64)
if __name__ == "__main__": unittest.main()
