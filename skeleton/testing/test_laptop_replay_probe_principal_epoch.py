"""Native SQLite replay is a private, exact-principal read even when absent.

All calls below run against a fake deterministic worker. They cannot
qualify GGUF model execution, installed source rights, laptop devices or
release, and cannot authorize a second native forward pass.
"""
from __future__ import annotations

from unittest import mock
import unittest

from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import ContractViolation
from skeleton.ai.runtime.operational_ai.laptop_runtime.replay_probe import inspect_replay
from skeleton.testing.laptop_runtime_test_support import FakeWorker, MODEL, TOKENIZER


class TestReadOnlyReplayEpoch(unittest.TestCase):
    def setUp(self):
        self.worker = FakeWorker()
        self.worker.spine.create("s_epoch")
        self.args = ("s_epoch", "r_epoch", "private offline prompt")

    def test_empty_read_never_allocates_or_generates(self):
        before = set(self.worker.spine.created)
        report = inspect_replay(self.worker, *self.args)
        self.assertIs(report["committed"], False)
        self.assertIs(report["no_second_generation"], True)
        self.assertEqual(self.worker.spine.created, before)
        self.assertEqual(self.worker.generation_calls, 0)

    def test_committed_receipt_is_read_without_native_generation(self):
        self.worker.turn(*self.args)
        before = self.worker.generation_calls
        result = inspect_replay(self.worker, *self.args)
        self.assertIs(result["committed"], True)
        self.assertIs(result["no_second_generation"], True)
        self.assertEqual(len(result["output_sha256"]), 64)
        self.assertEqual(self.worker.generation_calls, before)

    def test_model_swap_after_committed_read_denies_disclosure(self):
        self.worker.turn(*self.args)
        original = self.worker.spine.replay
        def change_model(*args, **kwargs):
            receipt = original(*args, **kwargs)
            self.worker.spine.backend.model_digest = "c" * 64
            return receipt
        with mock.patch.object(
            self.worker.spine, "replay", side_effect=change_model
        ):
            with self.assertRaises(ContractViolation):
                inspect_replay(self.worker, *self.args)
        self.assertEqual(self.worker.generation_calls, 1)

    def test_tokenizer_swap_after_committed_read_denies_disclosure(self):
        self.worker.turn(*self.args)
        original = self.worker.spine.replay
        def change_tokenizer(*args, **kwargs):
            receipt = original(*args, **kwargs)
            self.worker.spine.backend.tokenizer_digest = "d" * 64
            return receipt
        with mock.patch.object(
            self.worker.spine, "replay", side_effect=change_tokenizer
        ):
            with self.assertRaises(ContractViolation):
                inspect_replay(self.worker, *self.args)
        self.assertEqual(self.worker.generation_calls, 1)

    def test_tenant_swap_after_committed_read_denies_disclosure(self):
        self.worker.turn(*self.args)
        original = self.worker.spine.replay
        def change_tenant(*args, **kwargs):
            receipt = original(*args, **kwargs)
            self.worker.spine.identity.tenant = "foreign"
            return receipt
        with mock.patch.object(
            self.worker.spine, "replay", side_effect=change_tenant
        ):
            with self.assertRaisesRegex(ContractViolation, "principal changed"):
                inspect_replay(self.worker, *self.args)
        self.assertEqual(self.worker.generation_calls, 1)

    def test_subject_swap_after_missing_read_denies_empty_claim(self):
        original = self.worker.spine.replay
        def change_subject(*args, **kwargs):
            receipt = original(*args, **kwargs)
            self.worker.spine.identity.subject = "other"
            return receipt
        with mock.patch.object(
            self.worker.spine, "replay", side_effect=change_subject
        ):
            with self.assertRaisesRegex(ContractViolation, "empty durable replay"):
                inspect_replay(self.worker, *self.args)
        self.assertEqual(self.worker.generation_calls, 0)

    def test_tokenizer_swap_after_missing_read_denies_empty_claim(self):
        original = self.worker.spine.replay
        def change_tokenizer(*args, **kwargs):
            receipt = original(*args, **kwargs)
            self.worker.spine.backend.tokenizer_digest = "d" * 64
            return receipt
        with mock.patch.object(
            self.worker.spine, "replay", side_effect=change_tokenizer
        ):
            with self.assertRaises(ContractViolation):
                inspect_replay(self.worker, *self.args)
        self.assertEqual(self.worker.generation_calls, 0)

    def test_invalid_session_or_request_must_not_attempt_native_io(self):
        for index, invalid in enumerate((True, "", "bad/session", "x" * 129)):
            with self.subTest(invalid=repr(invalid)):
                with mock.patch.object(self.worker.spine, "replay") as replay:
                    with self.assertRaises(ContractViolation):
                        if index % 2:
                            inspect_replay(self.worker, invalid, "r_epoch", "text")
                        else:
                            inspect_replay(self.worker, "s_epoch", invalid, "text")
                    replay.assert_not_called()
        self.assertEqual(self.worker.generation_calls, 0)

    def test_unrelated_durable_request_is_not_a_committed_result(self):
        self.worker.turn(*self.args)
        report = inspect_replay(
            self.worker, "s_epoch", "r_other", "private offline prompt"
        )
        self.assertFalse(report["committed"])
        self.assertEqual(self.worker.generation_calls, 1)

    def test_valid_principal_identity_does_not_acquire_release_authority(self):
        self.worker.turn(*self.args)
        report = inspect_replay(self.worker, *self.args)
        self.assertTrue(report["committed"])
        self.assertNotIn("release_certified", report)
        self.assertNotIn("physical_device_qualified", report)
        self.assertEqual(self.worker.spine.identity.model_sha256, MODEL)
        self.assertEqual(self.worker.spine.identity.tokenizer_sha256, TOKENIZER)


if __name__ == "__main__":
    unittest.main()
