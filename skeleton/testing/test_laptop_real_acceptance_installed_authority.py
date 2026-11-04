"""No user-defined worker or self-reported source receipt can claim GGUF proof.

These tests are synthetic, validating denial semantics only. The production
success path requires activated model bytes, isolated child and SQL custody.
"""
from __future__ import annotations

import unittest

from skeleton.ai.runtime.operational_ai.deployment.install.doctor import (
    InstalledModelReport,
)
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.supervisor import (
    SupervisedAI,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.installed_witness import (
    require_activated_source,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.first_turn_acceptance import (
    run,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import (
    ContractViolation,
)
from skeleton.testing.laptop_runtime_test_support import (
    FakeWorker, MODEL, TOKENIZER,
)


def synthetic_receipt(**changed):
    fields = dict(
        model_id="fake-contract-only",
        model_sha256=MODEL,
        manifest_sha256="c" * 64,
        shard_count=1,
        model_bytes=4096,
        rights_approved=True,
        content_verified=True,
        native_inference_tested=False,
        release_certified=False,
        archive_sha256="d" * 64,
        source_sha="e" * 40,
    )
    fields.update(changed)
    return InstalledModelReport(**fields)


class TestInstalledProofBoundary(unittest.TestCase):
    def setUp(self):
        self.worker = FakeWorker()

    def test_forged_source_receipt_cannot_qualify_fake_worker(self):
        with self.assertRaisesRegex(
            ContractViolation, "canonical supervised native worker"
        ):
            require_activated_source(self.worker, synthetic_receipt())
        self.assertEqual(self.worker.generation_calls, 0)

    def test_self_reported_fake_worker_fields_do_not_upgrade_authority(self):
        self.worker.installed_source = synthetic_receipt()
        self.worker.source_approved = True
        self.worker.native_model_observed = True
        self.worker.device_qualified = True
        with self.assertRaises(ContractViolation):
            run(
                self.worker,
                prompt="private local request",
                approved=True,
                installed_receipt=synthetic_receipt(),
                require_real=True,
            )
        self.assertEqual(len(self.worker.spine.created), 0)
        self.assertEqual(self.worker.generation_calls, 0)

    def test_real_only_flag_rejects_missing_source_before_sqlite(self):
        with self.assertRaisesRegex(ContractViolation, "source proof required"):
            run(self.worker, prompt="private", approved=True, require_real=True)
        self.assertEqual(len(self.worker.spine.created), 0)
        self.assertEqual(self.worker.generation_calls, 0)

    def test_real_only_flag_is_not_truthy_coerced(self):
        for flag in (1, None, "true", [True], 0):
            with self.subTest(flag=repr(flag)):
                with self.assertRaises(ContractViolation):
                    run(self.worker, prompt="private", approved=True,
                        require_real=flag)
                self.assertEqual(self.worker.generation_calls, 0)

    def test_arbitrary_object_receipt_cannot_authorize_a_fake_native_process(self):
        for report in (object(), True, [], {}, "approved", synthetic_receipt()):
            with self.subTest(type=type(report).__name__):
                with self.assertRaises(ContractViolation):
                    run(self.worker, prompt="private", approved=True,
                        installed_receipt=report, require_real=True)
                self.assertEqual(len(self.worker.spine.created), 0)
                self.assertEqual(self.worker.generation_calls, 0)

    def test_wrong_spine_class_cannot_be_upgraded_by_wrapper(self):
        wrapped = SupervisedAI(self.worker.spine)
        with self.assertRaisesRegex(ContractViolation, "SQLite execution spine"):
            require_activated_source(wrapped, synthetic_receipt())
        self.assertEqual(self.worker.generation_calls, 0)

    def test_direct_synthetic_contract_does_not_claim_model_execution(self):
        result = run(
            self.worker, prompt="private local source-only task",
            approved=True,
        )
        self.assertEqual(result["model_sha256"], MODEL)
        self.assertEqual(result["tokenizer_sha256"], TOKENIZER)
        self.assertTrue(result["replayed_without_generation"])
        self.assertTrue(result["operator_approved_turn_attempt"])
        self.assertFalse(result["installed_source_bound"])
        self.assertFalse(result["native_model_observed"])
        self.assertFalse(result["operator_approved_real_inference"])
        self.assertEqual(
            result["evidence_grade"], "source-only-simulated-or-unverified"
        )
        self.assertIsNone(result["installed_source"])
        self.assertFalse(result["device_qualified"])
        self.assertFalse(result["release_certified"])
        self.assertEqual(self.worker.generation_calls, 1)

    def test_no_source_only_report_can_silently_become_a_release_pass(self):
        result = run(self.worker, prompt="task", approved=True)
        for label in (
            "source_rights_independently_verified",
            "physical_device_qualified",
            "windows_wsl2_qualified",
            "release_approved",
        ):
            with self.subTest(field=label):
                self.assertNotIn(label, result)
        self.assertIs(result["release_certified"], False)


if __name__ == "__main__":
    unittest.main()
