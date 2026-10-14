"""Draft #3544: drift must not publish a redundant checkpoint."""
from __future__ import annotations

import unittest

from skeleton.ai.model_runtime.admission_scheduler import RuntimeAdmissionScheduler
from skeleton.ai.model_runtime.replica_token_pin import ReplicaPinError, publish_pinned

DIGEST = "ab" * 32


class _Mem:
    def __init__(self, name: str) -> None:
        self.name = name
        self.failure_domain = name
        self.value = None

    def read(self):
        return self.value

    def write(self, snapshot) -> None:
        self.value = snapshot


class PinLaw(unittest.TestCase):
    def test_drift_does_not_publish(self) -> None:
        slots = [_Mem("a"), _Mem("b"), _Mem("c")]
        with self.assertRaises(ReplicaPinError):
            publish_pinned(RuntimeAdmissionScheduler(), slots, tokenizer_digest="cd" * 32, bound_digest=DIGEST)
        self.assertTrue(all(slot.value is None for slot in slots))

    def test_matching_digest_publishes(self) -> None:
        slots = [_Mem("a"), _Mem("b"), _Mem("c")]
        card = publish_pinned(RuntimeAdmissionScheduler(), slots, tokenizer_digest=DIGEST, bound_digest=DIGEST)
        self.assertEqual(card["stored_prose"], 0)
        self.assertEqual(card["tokenizer_digest"], DIGEST)
        self.assertIsNotNone(slots[0].value)


if __name__ == "__main__":
    unittest.main()
