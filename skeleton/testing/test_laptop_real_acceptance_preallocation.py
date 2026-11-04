"""First-turn native acceptance rejects invalid prompts before SQLite writes.

This uses a deliberately fake worker. It cannot qualify a real GGUF,
installed source rights, physical laptop, GPU or release approval.
"""
from __future__ import annotations
import unittest
from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import ContractViolation
from skeleton.ai.runtime.operational_ai.laptop_runtime.first_turn_acceptance import run
from skeleton.testing.laptop_runtime_test_support import FakeWorker, MODEL, TOKENIZER


class TestAcceptancePreallocation(unittest.TestCase):
    def setUp(self):
        self.worker = FakeWorker()

    def test_invalid_prompts_leave_zero_durable_session_state(self):
        invalid = (
            None, True, False, 1, [], {}, b"not-a-string", "",
            " \r\n ", "\x00", "prefix\x00suffix", "\ud800",
            "x" * (self.worker.spine.limits.input_bytes + 1),
        )
        for value in invalid:
            with self.subTest(value=repr(value)[:40]):
                with self.assertRaises(ContractViolation):
                    run(self.worker, prompt=value, approved=True)
                self.assertEqual(len(self.worker.spine.created), 0)
                self.assertEqual(len(self.worker.spine.receipts), 0)
                self.assertEqual(self.worker.generation_calls, 0)

    def test_not_approved_denies_without_native_or_sqlite(self):
        with self.assertRaisesRegex(ContractViolation, "approval"):
            run(self.worker, prompt="allowed local text")
        self.assertEqual(len(self.worker.spine.created), 0)
        self.assertEqual(self.worker.generation_calls, 0)

    def test_model_epoch_unavailable_before_new_durable_session(self):
        self.worker.spine.backend.model_digest = "d" * 64
        with self.assertRaises(ContractViolation):
            run(self.worker, prompt="valid but stale source", approved=True)
        self.assertEqual(len(self.worker.spine.created), 0)
        self.assertEqual(self.worker.generation_calls, 0)

    def test_valid_unicode_is_exactly_preserved_by_real_request_path(self):
        prompt = "Local first-turn private task: grønn skog 🌲"
        result = run(self.worker, prompt=prompt, approved=True)
        self.assertEqual(result["model_sha256"], MODEL)
        self.assertEqual(result["tokenizer_sha256"], TOKENIZER)
        self.assertTrue(result["replayed_without_generation"])
        self.assertFalse(result["operator_approved_real_inference"])
        self.assertFalse(result["native_model_observed"])
        self.assertFalse(result["installed_source_bound"])
        self.assertFalse(result["device_qualified"])
        self.assertFalse(result["release_certified"])
        self.assertEqual(self.worker.generation_calls, 1)
        self.assertEqual(len(self.worker.spine.created), 1)
        self.assertEqual(len(self.worker.spine.receipts), 1)
        native_key = next(iter(self.worker.spine.receipts))
        self.assertEqual(native_key[2], prompt)

    def test_exact_input_limit_never_truncates_or_mutates_prompt(self):
        prompt = "x" * self.worker.spine.limits.input_bytes
        result = run(self.worker, prompt=prompt, approved=True)
        self.assertGreater(result["generated_tokens"], 0)
        native_key = next(iter(self.worker.spine.receipts))
        self.assertEqual(native_key[2], prompt)
        self.assertEqual(self.worker.generation_calls, 1)

    def test_approval_requires_exact_boolean(self):
        for value in (1, "yes", [True], object()):
            with self.subTest(approved=type(value).__name__):
                with self.assertRaises(ContractViolation):
                    run(self.worker, prompt="valid", approved=value)
                self.assertEqual(len(self.worker.spine.created), 0)
                self.assertEqual(self.worker.generation_calls, 0)


if __name__ == "__main__":
    unittest.main()
