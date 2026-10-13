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
            "scheduled_test_module_count":2,
            "discovery_only_family_count":0,
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
                                 stdout="PASS",stderr="Ran 2 tests in 0.002s\n\nOK\n"),
                CompletedProcess(["python","-m","unittest"],0,
                                 stdout="",stderr="Ran 3 tests in 0.003s\n\nOK\n"),
            ]
            success=runner.produce(self.root,self.output,local=True)
            self.assertTrue(success)
            inventory.return_value.scan.assert_called_once()
        evidence=json.loads(self.output.read_text(encoding="utf-8"))
        self.assertEqual(evidence["git_head"],self.head)
        self.assertEqual(evidence["candidate_modules"],2)
        self.assertEqual(evidence["modules_actually_executed"],2)
        self.assertEqual(evidence["modules_reporting_pass"],2)
        self.assertEqual(evidence["total_unittest_cases_observed"],5)
        self.assertEqual([x["unittest_cases_observed"] for x in evidence["run_results"]],[2,3])
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
                CompletedProcess([],0,stdout="",stderr="Ran 1 test in 0.001s\nOK\n"),
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

    def test_unittest_zero_tests_is_not_accepted_as_working_feature(self):
        with (patch.dict(runner.os.environ,{"EXPECTED_SHA":self.head}),
              patch.object(runner,"_commit",return_value=self.head),
              patch.object(runner,"AppwideInventory"),
              patch.object(runner,"JeevesAcceptanceTestMatrix") as matrix,
              patch.object(runner.subprocess,"run") as execute):
            matrix.return_value.overview.return_value=self.matrix
            execute.side_effect=[
                CompletedProcess([],0,stdout="",stderr="Ran 0 tests in 0.000s\nOK\n"),
                CompletedProcess([],0,stdout="",stderr="Ran 1 test in 0.001s\nOK\n"),
            ]
            self.assertFalse(runner.produce(self.root,self.output,local=True))
        payload=json.loads(self.output.read_text())
        self.assertEqual(payload["modules_reporting_pass"],1)
        self.assertIsNone(payload["run_results"][0]["unittest_cases_observed"])
        self.assertFalse(payload["selected_regression_suite_reported_success"])

    def test_missing_actual_unittest_test_count_fails_closed(self):
        self.assertIsNone(runner._observed_unittest_count(""))
        self.assertIsNone(runner._observed_unittest_count("OK"))
        self.assertIsNone(runner._observed_unittest_count("Ran 0 tests in 0.001s"))
        self.assertIsNone(runner._observed_unittest_count(
            "Ran 2 tests in 0.001s\nRan 2 tests in 0.001s"))
        self.assertEqual(runner._observed_unittest_count(
            "Ran 1 test in 0.001s\n\nOK"),1)
        self.assertEqual(runner._observed_unittest_count(
            "Ran 50 tests in 0.145s\n\nOK"),50)

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

    def test_ci_repository_and_workflow_cannot_be_suffix_spoofed(self):
        known={
            "CI":"true",
            "GITHUB_ACTIONS":"true",
            "EXPECTED_SHA":self.head,
            "GITHUB_RUN_ID":"12345",
            "GITHUB_RUN_ATTEMPT":"1",
            "GITHUB_REPOSITORY":"other/Skeleton",
            "GITHUB_WORKFLOW":"Jeeves App Acceptance Matrix",
            "RUNNER_OS":"Linux",
        }
        with patch.object(runner,"_commit",return_value=self.head):
            for corrupt in (
                {"GITHUB_REPOSITORY":"other/Skeleton"},
                {"GITHUB_WORKFLOW":"Unreviewed CI Pipeline"},
                {"RUNNER_OS":"Unknown"},
                {"GITHUB_RUN_ID":"bad-id"},
                {"CI":"false"},
            ):
                environment={**known,**corrupt}
                with self.subTest(corrupt=corrupt),patch.dict(
                    runner.os.environ,environment,clear=True):
                    with self.assertRaises(RuntimeError):
                        runner.produce(self.root,self.output,local=False)
        self.assertFalse(self.output.exists())

    def test_output_must_remain_inside_workspace(self):
        elsewhere=Path(self.tmp.name).parent/"external_evidence.json"
        with (patch.dict(runner.os.environ,{"EXPECTED_SHA":self.head}),
              patch.object(runner,"_commit",return_value=self.head),
              patch.object(runner,"AppwideInventory"),
              patch.object(runner,"JeevesAcceptanceTestMatrix") as matrix,
              patch.object(runner.subprocess,"run") as execute):
            matrix.return_value.overview.return_value=self.matrix
            execute.side_effect=[CompletedProcess([],0,"","Ran 2 tests in 0.001s\nOK\n"),
                                 CompletedProcess([],0,"","Ran 2 tests in 0.001s\nOK\n")]
            with self.assertRaises(RuntimeError):
                runner.produce(self.root,elsewhere,local=True)
        self.assertFalse(elsewhere.exists())


if __name__ == "__main__":
    unittest.main()
