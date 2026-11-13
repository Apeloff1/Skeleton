"""First-laptop cold-reopen source, identity and replay boundary tests.

Only the fake native worker is used; these cannot prove real GGUF inference,
hardware fitness, third-party model rights or release. All successful
production evidence requires the installed isolated model and SQLite spine.
"""
from __future__ import annotations

from unittest import mock
import unittest

from skeleton.ai.runtime.operational_ai.laptop_runtime import (
    cold_reopen_acceptance,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import ContractViolation
from skeleton.testing.laptop_runtime_test_support import FakeWorker, MODEL, TOKENIZER
from skeleton.testing.test_laptop_cold_reopen_source_custody import (
    SyntheticColdRig, SOURCE, OPTS,
)


class ColdPrincipalGuardTests(unittest.TestCase):
    def test_first_activation_wrong_tenant_refused_before_sqlite_session(self):
        rig = SyntheticColdRig()
        rig.first.spine.identity.tenant = "foreign"
        with rig.patch() as (activated, initial, reopened):
            with self.assertRaisesRegex(
                ContractViolation, "first native worker belongs to another principal"
            ):
                cold_reopen_acceptance.run(**OPTS)
        self.assertEqual(activated.call_count, 1)
        initial.assert_not_called()
        reopened.assert_not_called()
        self.assertEqual(len(rig.first.spine.created), 0)
        self.assertEqual(rig.first.generation_calls, 0)
        self.assertIn("closed_1", rig.order)

    def test_first_activation_wrong_subject_refused_before_native_call(self):
        rig = SyntheticColdRig()
        rig.first.spine.identity.subject = "foreign"
        with rig.patch() as (activated, _, _):
            with self.assertRaisesRegex(ContractViolation, "another principal"):
                cold_reopen_acceptance.run(**OPTS)
        self.assertEqual(activated.call_count, 1)
        self.assertFalse(rig.first.spine.created)
        self.assertEqual(rig.first.generation_calls, 0)

    def test_second_activation_wrong_tenant_refused_before_replay(self):
        rig = SyntheticColdRig()
        def replace_tenant():
            rig.first.spine.identity.tenant = "foreign"
            def forbidden_replay(*args, **kwargs):
                self.fail("foreign tenant must not read SQLite replay")
            rig.first.spine.replay = forbidden_replay
        rig.after_first = replace_tenant
        with rig.patch():
            with self.assertRaisesRegex(
                ContractViolation, "cold native worker belongs to another principal"
            ):
                cold_reopen_acceptance.run(**OPTS)
        self.assertEqual(rig.first.generation_calls, 1)
        self.assertEqual(rig.second.generation_calls, 0)
        self.assertIn("closed_2", rig.order)

    def test_second_activation_wrong_subject_refused_before_replay(self):
        rig = SyntheticColdRig()
        def replace_subject():
            rig.first.spine.identity.subject = "foreign"
            rig.first.spine.replay = lambda *a, **k: self.fail(
                "foreign subject must not read SQLite replay"
            )
        rig.after_first = replace_subject
        with rig.patch():
            with self.assertRaisesRegex(
                ContractViolation, "cold native worker belongs to another principal"
            ):
                cold_reopen_acceptance.run(**OPTS)
        self.assertEqual(rig.first.generation_calls, 1)
        self.assertEqual(rig.second.generation_calls, 0)
        self.assertIn("closed_2", rig.order)

    def test_second_worker_same_model_does_not_grant_owner_change(self):
        rig = SyntheticColdRig()
        rig.after_first = lambda: setattr(
            rig.first.spine.identity, "subject", "other"
        )
        with rig.patch():
            with self.assertRaises(ContractViolation):
                cold_reopen_acceptance.run(**OPTS)
        self.assertEqual(rig.first.spine.identity.model_sha256, MODEL)
        self.assertEqual(rig.first.spine.identity.tokenizer_sha256, TOKENIZER)
        self.assertEqual(rig.first.generation_calls, 1)
        self.assertEqual(rig.second.generation_calls, 0)

    def test_normal_owner_match_still_has_exact_one_native_generation(self):
        rig = SyntheticColdRig()
        with rig.patch():
            record = cold_reopen_acceptance.run(**OPTS)
        self.assertEqual(rig.first.generation_calls, 1)
        self.assertEqual(rig.second.generation_calls, 0)
        self.assertTrue(record["sqlite_replay_after_cold_reopen"])
        self.assertFalse(record["release_certified"])


if __name__ == "__main__":
    unittest.main()
