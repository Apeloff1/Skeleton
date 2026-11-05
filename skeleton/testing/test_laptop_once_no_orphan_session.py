"""Admission ordering for canonical local-first one-shot native inference.

The in-memory worker is a test double; results are not installed GGUF,
rights review, device qualification or release certification.
"""
from __future__ import annotations

from unittest import mock
import unittest

from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import (
    ContractViolation,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.run_once import (
    generate_once,
)
from skeleton.testing.laptop_runtime_test_support import (
    FakeWorker, MODEL, TOKENIZER, OUTPUT_SHA,
)


class OneShotNoOrphans(unittest.TestCase):
    def setUp(self):
        self.worker = FakeWorker()

    def test_invalid_caller_request_id_does_not_allocate_session(self):
        for value in (True, 0, "", "bad/request", [], None if False else "a"*500):
            with self.subTest(value=repr(value)):
                with self.assertRaises(ContractViolation):
                    generate_once(self.worker, "private local prompt", request_id=value)
                self.assertFalse(self.worker.spine.created)
                self.assertFalse(self.worker.spine.receipts)
                self.assertEqual(self.worker.generation_calls,0)

    def test_invalid_supplied_session_cannot_create_new_session(self):
        for value in (False, 0, "", "bad/session", [], "s"*600):
            with self.subTest(value=repr(value)):
                with self.assertRaises(ContractViolation):
                    generate_once(
                        self.worker, "private prompt", session=value,
                        request_id="valid",
                    )
                self.assertFalse(self.worker.spine.created)
                self.assertEqual(self.worker.generation_calls,0)

    def test_unreadable_prompt_does_not_create_new_session(self):
        for value in ("", "  ", "\x00", None, [], b"private bytes", "a"*32769):
            with self.subTest(value=type(value).__name__):
                with self.assertRaises(ContractViolation):
                    generate_once(self.worker, value, request_id="healthy")
                self.assertEqual(len(self.worker.spine.created),0)
                self.assertEqual(self.worker.generation_calls,0)

    def test_invalid_seed_cannot_leave_orphan(self):
        for value in (True, False, -1, 2**32, "0", None):
            with self.subTest(seed=value):
                with self.assertRaises(ContractViolation):
                    generate_once(self.worker, "valid", seed=value)
                self.assertFalse(self.worker.spine.created)
                self.assertEqual(self.worker.generation_calls,0)

    def test_invalid_temperature_cannot_leave_orphan(self):
        for value in (0, -1, 2.1, True, False, "0.8", None, float("nan")):
            with self.subTest(temperature=str(value)):
                with self.assertRaises(ContractViolation):
                    generate_once(self.worker,"valid",temperature=value)
                self.assertFalse(self.worker.spine.created)
                self.assertEqual(self.worker.generation_calls,0)

    def test_bad_sampler_with_valid_user_request_id_denies_before_create(self):
        with self.assertRaises(ContractViolation):
            generate_once(
                self.worker, "private test",
                request_id="well_formed_id", temperature=float("inf"),
            )
        self.assertFalse(self.worker.spine.created)
        self.assertFalse(self.worker.spine.receipts)

if __name__ == "__main__":
    unittest.main()
