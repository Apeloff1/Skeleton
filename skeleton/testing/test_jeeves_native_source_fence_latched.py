"""Monotonic live GGUF source lease revocation, no synthetic promotion.

All model/source witnesses are TEST DOUBLES and never qualify installed
weights, real inference, third-party rights, hardware or release.
"""
from __future__ import annotations

from threading import Event, Thread
from unittest import mock
import unittest

from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import ContractViolation
from skeleton.jeeves.agent.native_source_fence import NativeSourceFence
from skeleton.testing.test_jeeves_native_provider_bridge import SimulatedWorker, MODEL, TOKENIZER

SOURCE = {
    "model_sha256": MODEL, "tokenizer_sha256": TOKENIZER,
    "manifest_sha256": "c"*64, "archive_sha256": "d"*64,
    "source_sha": "e"*40, "installed_model_bytes": 1024,
    "installed_shard_count": 1,
}


def new_fence(worker):
    with mock.patch(
        "skeleton.jeeves.agent.native_source_fence.require_activated_source",
        return_value=dict(SOURCE),
    ):
        return NativeSourceFence(
            worker, object(), expected_tenant="local",
            expected_subject="operator",
        )


class MonotonicSourceFenceTests(unittest.TestCase):
    def setUp(self):
        self.worker=SimulatedWorker()
        self.fence=new_fence(self.worker)

    def test_healthy_fence_is_read_only_and_not_release_qualified(self):
        with mock.patch(
            "skeleton.jeeves.agent.native_source_fence.require_activated_source",
            return_value=dict(SOURCE),
        ) as witness:
            self.fence.assert_live(self.worker)
            self.fence.assert_live(self.worker)
        self.assertEqual(witness.call_count, 2)
        self.assertIs(self.fence.release_certified, False)
        self.assertEqual(self.worker.spine.generations, 0)

    def test_lease_failure_is_permanent_after_source_restored(self):
        with mock.patch(
            "skeleton.jeeves.agent.native_source_fence.require_activated_source",
            side_effect=[ContractViolation("lease revoked"), dict(SOURCE)],
        ) as witness:
            with self.assertRaises(ContractViolation):
                self.fence.assert_live(self.worker)
            with self.assertRaisesRegex(ContractViolation, "permanently revoked"):
                self.fence.assert_live(self.worker)
        self.assertEqual(witness.call_count, 1)
        self.assertEqual(self.worker.spine.generations, 0)

    def test_archive_mismatch_latches_even_when_subsequently_repaired(self):
        with mock.patch(
            "skeleton.jeeves.agent.native_source_fence.require_activated_source",
            side_effect=[
                {**SOURCE, "archive_sha256": "f"*64},
                dict(SOURCE),
            ],
        ) as witness:
            with self.assertRaisesRegex(ContractViolation, "source"):
                self.fence.assert_live(self.worker)
            with self.assertRaisesRegex(ContractViolation, "permanently revoked"):
                self.fence.assert_live(self.worker)
        self.assertEqual(witness.call_count, 1)

    def test_model_epoch_change_latches_without_source_inspection(self):
        self.worker.spine.backend.model_digest="f"*64
        with mock.patch(
            "skeleton.jeeves.agent.native_source_fence.require_activated_source",
        ) as witness:
            with self.assertRaises(ContractViolation):
                self.fence.assert_live(self.worker)
            witness.assert_not_called()
            self.worker.spine.backend.model_digest=MODEL
            with self.assertRaisesRegex(ContractViolation, "permanently revoked"):
                self.fence.assert_live(self.worker)
        self.assertEqual(self.worker.spine.generations, 0)

    def test_foreign_worker_attempt_revokes_fence_for_original_too(self):
        other=SimulatedWorker()
        with self.assertRaisesRegex(ContractViolation, "different native worker"):
            self.fence.assert_live(other)
        with self.assertRaisesRegex(ContractViolation, "permanently revoked"):
            self.fence.assert_live(self.worker)

    def test_concurrent_native_reads_cannot_undo_revocation(self):
        entered=Event()
        release=Event()
        errors=[]
        def revoke(*_args):
            entered.set()
            if not release.wait(5):
                raise ContractViolation("bounded synthetic gate timeout")
            raise ContractViolation("native source removed")
        def inspect():
            try:
                self.fence.assert_live(self.worker)
            except BaseException as exc:
                errors.append(type(exc).__name__)
        with mock.patch(
            "skeleton.jeeves.agent.native_source_fence.require_activated_source",
            side_effect=revoke,
        ) as witness:
            first=Thread(target=inspect,daemon=True)
            second=Thread(target=inspect,daemon=True)
            first.start()
            self.assertTrue(entered.wait(5))
            second.start()
            release.set()
            first.join(5)
            second.join(5)
            self.assertFalse(first.is_alive() or second.is_alive())
        self.assertEqual(len(errors),2)
        self.assertEqual(witness.call_count,1)
        self.assertEqual(self.worker.spine.generations,0)

    def test_bad_shape_after_live_read_revokes_fence(self):
        with mock.patch(
            "skeleton.jeeves.agent.native_source_fence.require_activated_source",
            side_effect=[dict(SOURCE), {**SOURCE,"installed_shard_count":True},
                         dict(SOURCE)],
        ) as witness:
            self.fence.assert_live(self.worker)
            with self.assertRaises(ContractViolation):
                self.fence.assert_live(self.worker)
            with self.assertRaisesRegex(ContractViolation,"permanently revoked"):
                self.fence.assert_live(self.worker)
        self.assertEqual(witness.call_count,2)


if __name__ == "__main__":
    unittest.main()
