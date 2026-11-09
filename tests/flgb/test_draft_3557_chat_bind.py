"""Draft #3557: chat admission must carry the tokenizer digest."""
from __future__ import annotations

import unittest

from skeleton.ai.model_runtime.admission_scheduler import RuntimeAdmissionScheduler
from skeleton.ai.model_runtime.chat_admission_bind import ChatAdmissionGate, ChatBindError
from skeleton.ai.model_runtime.flgb_model_runtime import BatchRequest

DIGEST = "ab" * 32


class ChatLaw(unittest.TestCase):
    def test_drift_does_not_queue(self) -> None:
        gate = ChatAdmissionGate(RuntimeAdmissionScheduler(), DIGEST)
        with self.assertRaises(ChatBindError):
            gate.submit(BatchRequest("req", 4, 2), kv_bytes=64, tokenizer_digest="cd" * 32)
        queued = gate.scheduler.queued_ids
        queued = queued() if callable(queued) else queued
        self.assertEqual(queued, ())

    def test_match_queues(self) -> None:
        gate = ChatAdmissionGate(RuntimeAdmissionScheduler(), DIGEST)
        card = gate.submit(BatchRequest("req", 4, 2), kv_bytes=64, tokenizer_digest=DIGEST)
        self.assertEqual(card.card()["stored_prose"], 0)
        queued = gate.scheduler.queued_ids
        queued = queued() if callable(queued) else queued
        self.assertEqual(queued, ("req",))


if __name__ == "__main__":
    unittest.main()
