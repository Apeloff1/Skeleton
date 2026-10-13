"""Runner evidence integrity; never confuse test subprocesses with CI provenance."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from subprocess import CompletedProcess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import run_app_acceptance_matrix as runner


class AcceptanceRunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        (self.root/".git").mkdir()
        self.output=self.root/"build"/"test_evidence.json"
        self.head="a"*40
        self.matrix={
            "inventory_snapshot":"b"*64,
            "digest":"c"*64,
            "matrix_sha256":"d"*64,
            "scope_sha256":"e"*64,
            "curated_test_family_count":2,
            "family_denominator":42,
            "unique_test_module_count":2,
            "selected_modules":["tests.test_alpha","tests.test_beta"],
            "module_source_receipts":[
                {"path":"tests/test_alpha.py","sha256":"f"*64,
                 "declared_test_case_count":2},
                {"path":"tests/test_beta.py","sha256":"0"*64,
                 "declared_test_case_count":3},
            ],
        }

    def test_module_output_is_redacted_but_identifiable(self):
        private="Authorization: Bearer SUPER_SECRET_DO_NOT_PERSIST"
        receipt=runner._safe_output(private)
        self.assertEqual(receipt["total_bytes"],len(private.encode()))
        self.assertEqual(receipt["sha256"],sha256(private.encode()).hexdigest())
        self.assertFalse(receipt["content_stored_in_artifact"])
        self.assertNotIn("excerpt",receipt)
        self.assertNotIn("SUPER_SECRET",json.dumps(receipt))

    def test_local_two_module_run_produces_auditable_but_untrusted_evidence(self):
        with (patch.dict(runner.os.environ,{"EXPECTED_SHA":self.head}),
              patch.object(runner,"_commit",return_value=self.head),
              patch.object(runner,"AppwideInventory") as inventory,
              patch.object(runner,"JeevesAcceptanceTestMatrix") as matrix,
              patch.object(runner.subprocess,"run") as execute):
            matrix.return_value.overview.return_value=self.matrix
            execute.side_effect=[
                CompletedProcess(["python","-m","unittest"],0,
                                 stdout="PASS",stderr=""),
                CompletedProcess(["python","-m","unittest"],0,
                                 stdout="",stderr="OK"),
            ]
            success=runner.produce(self.root,self.output,local=True)
            self.assertTrue(success)
            inventory.return_value.scan.assert_called_once()
        evidence=json.loads(self.output.read_text(encoding="utf-8"))
        self.assertEqual(evidence["git_head"],self.head)
        self.assertEqual(evidence["candidate_modules"],2)
        self.assertEqual(evidence["modules_actually_executed"],2)
        self.assertEqual(evidence["modules_reporting_pass"],2)
        self.assertTrue(evidence["selected_regression_suite_reported_success"])
        self.assertFalse(evidence["independent_github_run_identity_verified_externally"])
        self.assertFalse(evidence["release_device_verified"])
        self.assertFalse(evidence["user_journeys_verified"])
        self.assertIsNone(evidence["full_app_completion_percent"])
        self.assertEqual(evidence["curated_family_count"],2)
        self.assertEqual(evidence["full_family_denominator"],42)
        self.assertNotIn("stdout",json.dumps(evidence["run_results"][0]["stdout"]))

    def test_one_failing_module_does_not_forge_batch_pass(self):
        with (patch.dict(runner.os.environ,{"EXPECTED_SHA":self.head}),
              patch.object(runner,"_commit",return_value=self.head),
              patch.object(runner,"AppwideInventory"),
              patch.object(runner,"JeevesAcceptanceTestMatrix") as matrix,
              patch.object(runner.subprocess,"run") as execute):
            matrix.return_value.overview.return_value=self.matrix
            execute.side_effect=[
                CompletedProcess([],0,stdout="",stderr=""),
                CompletedProcess([],1,stdout="",stderr="Traceback"),
            ]
            success=runner.produce(self.root,self.output,local=True)
        self.assertFalse(success)
        receipt=json.loads(self.output.read_text(encoding="utf-8"))
        self.assertEqual(receipt["modules_actually_executed"],2)
        self.assertEqual(receipt["modules_reporting_pass"],1)
        self.assertFalse(receipt["selected_regression_suite_reported_success"])
        self.assertFalse(receipt["run_results"][1]["targeted_tests_passed_in_runner"])
        self.assertNotIn("Traceback",json.dumps(receipt))

    def test_ci_mode_without_exact_provenance_rejected_before_imports(self):
        with patch.object(runner,"_commit",return_value=self.head):
            with patch.dict(runner.os.environ,{"CI":"","GITHUB_ACTIONS":"",
                                            "EXPECTED_SHA":"b"*40},clear=True):
                with self.assertRaises(RuntimeError):
                    runner.produce(self.root,self.output,local=False)
        self.assertFalse(self.output.exists())

    def test_local_expected_commit_mismatch_fails_before_test_execution(self):
        with patch.object(runner,"_commit",return_value=self.head):
            with patch.dict(runner.os.environ,{"EXPECTED_SHA":"b"*40},clear=True):
                with self.assertRaises(RuntimeError):
                    runner.produce(self.root,self.output,local=True)
        self.assertFalse(self.output.exists())

    def test_output_must_remain_inside_workspace(self):
        elsewhere=Path(self.tmp.name).parent/"external_evidence.json"
        with (patch.dict(runner.os.environ,{"EXPECTED_SHA":self.head}),
              patch.object(runner,"_commit",return_value=self.head),
              patch.object(runner,"AppwideInventory"),
              patch.object(runner,"JeevesAcceptanceTestMatrix") as matrix,
              patch.object(runner.subprocess,"run") as execute):
            matrix.return_value.overview.return_value=self.matrix
            execute.side_effect=[CompletedProcess([],0,"",""),
                                 CompletedProcess([],0,"","")]
            with self.assertRaises(RuntimeError):
                runner.produce(self.root,elsewhere,local=True)
        self.assertFalse(elsewhere.exists())


if __name__ == "__main__":
    unittest.main()
