"""Serving audit chain verification and adversarial tamper tests."""
from dataclasses import replace
import unittest

from skeleton.ai.model_serving.audit import (
    AuditError, ServingAuditChain,
)

D1 = "a" * 64
D2 = "b" * 64


class AuditTests(unittest.TestCase):
    def test_chain_and_tampering(self):
        chain = ServingAuditChain()
        first = chain.append(request_digest=D1, action="admission", outcome="accepted")
        second = chain.append(request_digest=D1, action="reservation", outcome="accepted")
        third = chain.append(request_digest=D2, action="terminal", outcome="failed")
        original = chain.snapshot()
        self.assertTrue(chain.verify(original))
        self.assertEqual(second.predecessor, first.digest)
        self.assertEqual(third.predecessor, second.digest)
        self.assertEqual(len({x.digest for x in original}), 3)
        for tampered in (
            (replace(first, outcome="denied"), second, third),
            (first, replace(second, request_digest=D2), third),
            (first, replace(second, predecessor=D2), third),
            (first, replace(second, digest=D2), third),
            (first, replace(second, sequence=9), third),
            (first, third),
            (third, second, first),
        ):
            with self.subTest(tampered=tampered):
                self.assertFalse(chain.verify(tampered))

    def test_bounded_and_invalid_events(self):
        chain = ServingAuditChain(max_receipts=1)
        for values in (
            {"request_digest": "bad", "action": "admission", "outcome": "accepted"},
            {"request_digest": D1, "action": "unknown", "outcome": "accepted"},
            {"request_digest": D1, "action": "terminal", "outcome": "unknown"},
        ):
            with self.assertRaises(AuditError):
                chain.append(**values)
        chain.append(request_digest=D1, action="admission", outcome="accepted")
        with self.assertRaises(AuditError):
            chain.append(request_digest=D2, action="terminal", outcome="completed")
        self.assertEqual(len(chain.snapshot()), 1)
        self.assertFalse(chain.verify(list(chain.snapshot())))
        with self.assertRaises(AuditError):
            ServingAuditChain(max_receipts=True)


if __name__ == "__main__":
    unittest.main()
