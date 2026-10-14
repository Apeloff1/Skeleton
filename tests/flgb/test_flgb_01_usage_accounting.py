import unittest
from skeleton.inference.usage_accounting import UsageLedger
class TestUsageAccounting(unittest.TestCase):
    def test_accumulation(self):
        ledger = UsageLedger("op").append(10, 2, 4).append(0, 3, 5)
        self.assertEqual((ledger.input_tokens, ledger.output_tokens, ledger.cost_micro_units), (10, 5, 9))
        self.assertEqual(ledger.usage.attempts, 2)
if __name__ == "__main__": unittest.main()
