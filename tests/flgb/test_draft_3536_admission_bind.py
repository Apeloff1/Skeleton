"""Draft #3536: a submit without the bound tokenizer digest must not queue."""
from __future__ import annotations

import unittest

from skeleton.ai.model_runtime.admission_scheduler import RuntimeAdmissionScheduler
from skeleton.ai.model_runtime.admission_token_bind import AdmissionBindError, AdmissionIdentityGate
from skeleton.ai.model_runtime.flgb_model_runtime import BatchRequest

DIGEST = "ab" * 32


class BindLaw(unittest.TestCase):
    def test_drift_does_not_queue(self) -> None:
        gate = AdmissionIdentityGate(RuntimeAdmissionScheduler(), DIGEST)
        request = BatchRequest("req-1", 4, 2)
        with self.assertRaises(AdmissionBindError):
            gate.submit(request, kv_bytes=128, tokenizer_digest="cd" * 32)
        self.assertEqual(gate.scheduler.queued_ids, ())

    def test_bound_submit_is_required_later(self) -> None:
        gate = AdmissionIdentityGate(RuntimeAdmissionScheduler(), DIGEST)
        request = BatchRequest("req-2", 4, 2)
        bound = gate.submit(request, kv_bytes=128, tokenizer_digest=DIGEST)
        self.assertEqual(bound.card()["stored_prose"], 0)
        self.assertEqual(gate.scheduler.queued_ids, ("req-2",))
        gate.require("req-2", bound.digest)
        with self.assertRaises(AdmissionBindError):
            gate.require("req-2", "cd" * 32)


if __name__ == "__main__":
    unittest.main()
