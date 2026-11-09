import unittest
from skeleton.inference.deadline import DeadlineBudget, DeadlineExceeded
class TestDeadline(unittest.TestCase):
    def test_explicit_reserve(self):
        budget = DeadlineBudget("op", 100)
        self.assertEqual(budget.require_remaining(20, 10), 70)
        with self.assertRaises(DeadlineExceeded):
            budget.require_remaining(90, 10)
if __name__ == "__main__": unittest.main()
