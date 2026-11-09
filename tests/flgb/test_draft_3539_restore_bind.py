"""Draft #3539: restore must be pinned to a tokenizer digest."""
from __future__ import annotations

import unittest

from skeleton.ai.model_runtime.admission_scheduler import RuntimeAdmissionScheduler
from skeleton.ai.model_runtime.flgb_model_runtime import BatchRequest
from skeleton.ai.model_runtime.restore_token_bind import RestoreBindError, restore_bound, same_identity

DIGEST = "ab" * 32


class RestoreBind(unittest.TestCase):
    def test_restore_pins_digest(self) -> None:
        sched = RuntimeAdmissionScheduler()
        sched.submit(BatchRequest("req", 4, 2), kv_bytes=128)
        card = restore_bound(sched.snapshot(), tokenizer_digest=DIGEST)
        self.assertEqual(card["stored_prose"], 0)
        self.assertEqual(card["tokenizer_digest"], DIGEST)
        self.assertEqual(card["scheduler"].queued_ids, ("req",))
        with self.assertRaises(RestoreBindError):
            same_identity(DIGEST, "cd" * 32)

    def test_bad_digest_does_not_restore(self) -> None:
        sched = RuntimeAdmissionScheduler()
        with self.assertRaises(RestoreBindError):
            restore_bound(sched.snapshot(), tokenizer_digest="nope")


if __name__ == "__main__":
    unittest.main()
