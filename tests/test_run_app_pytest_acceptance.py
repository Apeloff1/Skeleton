"""Real pytest acceptance enforcement: XML counters, run isolation and custody."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from subprocess import CompletedProcess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from skeleton.ai.game_builder.jeeves_appwide_fabric import JeevesAppwideError
from scripts import run_app_pytest_acceptance as runner


def xml(tests=2, failures=0, skipped=0, errors=0, actual=None, bad=False):
    if actual is None:
        actual=tests
    content=[
        f'<testsuites><testsuite name="pytest" tests="{tests}" '
        f'failures="{failures}" errors="{errors}" skipped="{skipped}">'
    ]
    for i in range(actual):
        content.append(
            f'<testcase classname="tests.test_unit" name="test_real_{i}">'
            + ('<skipped/>' if bad and i==0 else '') + '</testcase>'
        )
    return ''.join(content) + '</testsuite></testsuites>'


class PytestAcceptanceRunnerTests(unittest.TestCase):
    def setUp(self):
        temp=TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        (self.root/".git").mkdir()
        self.out=self.root/"build"/"pytest.json"
        self.sha="f"*40
        self.project={
            "pytest_selected_modules":["tests.test_real_pytest_a",
                                       "tests.test_real_pytest_b"],
            "scheduled_pytest_module_count":2,
            "pytest_smoke_family_count":2,
            "selected_modules":["tests.test_real_unittest"],
            "module_source_receipts":[
                {"path":"tests/test_real_pytest_a.py","sha256":"1"*64,
                 "declared_test_case_count":2},
                {"path":"tests/test_real_pytest_b.py","sha256":"2"*64,
                 "declared_test_case_count":2},
            ],
            "inventory_snapshot":"1"*64,"digest":"2"*64,
            "matrix_sha256":"3"*64,"scope_sha256":"4"*64,
            "family_denominator":42,
        }

    def test_XML_two_actual_positive_cases_are_real(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/"report.xml"
            path.write_text(xml())
            result=runner._junit_cases(path)
        self.assertEqual(result["cases_executed"],2)
        self.assertEqual(result["cases_skipped"],0)
        self.assertTrue(result["tests_run_in_real_pytest"])
        self.assertEqual(len(result["xml_sha256"]),64)

    def test_skip_failure_error_or_zero_cannot_count_as_pass(self):
        for variant in (
            {"tests":0},
            {"tests":2,"skipped":1,"bad":True},
            {"tests":2,"failures":1},
            {"tests":2,"errors":1},
            {"tests":2,"actual":1},
            {"tests":2001,"actual":1},
        ):
            with self.subTest(variant=variant),TemporaryDirectory() as directory:
                file=Path(directory)/"output.xml"
                file.write_text(xml(**variant))
                with self.assertRaises(JeevesAppwideError):
                    runner._junit_cases(file)

    def test_DTD_entity_and_untrusted_XML_rejected(self):
        for attack in (
            "<!DOCTYPE testsuites [<!ENTITY x SYSTEM 'file:///etc/passwd'>]>"
            +xml(),
            "<?xml version='1.0'?><!ENTITY x 'boom'>"+xml(),
            '<other tests="1"></other>',
            '<testsuites><testsuite tests="1"></testsuite><testsuite tests="1"></testsuite></testsuites>',
            "not XML"
        ):
            with TemporaryDirectory() as directory:
                file=Path(directory)/"test.xml"
                file.write_text(attack)
                with self.assertRaises(JeevesAppwideError):
                    runner._junit_cases(file)

    def test_positive_two_real_subprocesses_emit_source_bound_candidate(self):
        def execute(argv,**kwargs):
            xml_file=Path(next(arg.split("=",1)[1] for arg in argv
                               if arg.startswith("--junitxml=")))
            xml_file.write_text(xml(tests=2))
            return CompletedProcess(argv,0,
                                    stdout="2 passed SECRET_SHOULD_NOT_LEAK",
                                    stderr="")
        with (patch.dict(runner.os.environ,{"EXPECTED_SHA":self.sha},clear=True),
              patch.object(runner,"_commit",return_value=self.sha),
              patch.object(runner,"AppwideInventory") as inventory,
              patch.object(runner,"JeevesAcceptanceTestMatrix") as matrix,
              patch.object(runner.subprocess,"run",side_effect=execute)):
            matrix.return_value.overview.return_value=self.project
            self.assertTrue(runner.produce(self.root,self.out,local=True))
            inventory.return_value.scan.assert_called_once()
        report=json.loads(self.out.read_text())
        self.assertEqual(report["modules_actually_executed"],2)
        self.assertEqual(report["modules_reporting_pass"],2)
        self.assertEqual(report["pytest_cases_observed_total"],4)
        self.assertTrue(report["selected_regression_suite_reported_success"])
        self.assertIsNone(report["full_app_completion_percent"])
        self.assertFalse(report["release_device_verified"])
        self.assertFalse(report["independent_github_run_identity_verified_externally"])
        self.assertNotIn("SECRET_SHOULD_NOT_LEAK",json.dumps(report))
        self.assertEqual([x["pytest_cases_observed"] for x in report["run_results"]],
                         [2,2])

    def test_return_code_zero_without_XML_must_fail_batch(self):
        with (patch.dict(runner.os.environ,{"EXPECTED_SHA":self.sha},clear=True),
              patch.object(runner,"_commit",return_value=self.sha),
              patch.object(runner,"AppwideInventory"),
              patch.object(runner,"JeevesAcceptanceTestMatrix") as matrix,
              patch.object(runner.subprocess,"run") as execute):
            matrix.return_value.overview.return_value=self.project
            execute.return_value=CompletedProcess([],0,"2 passed","")
            self.assertFalse(runner.produce(self.root,self.out,local=True))
        body=json.loads(self.out.read_text())
        self.assertEqual(body["modules_reporting_pass"],0)
        self.assertEqual(body["pytest_cases_observed_total"],0)
        self.assertFalse(body["selected_regression_suite_reported_success"])

    def test_unreviewed_duplicate_runner_module_rejected(self):
        self.project["selected_modules"].append("tests.test_real_pytest_a")
        with (patch.dict(runner.os.environ,{"EXPECTED_SHA":self.sha},clear=True),
              patch.object(runner,"_commit",return_value=self.sha),
              patch.object(runner,"AppwideInventory"),
              patch.object(runner,"JeevesAcceptanceTestMatrix") as matrix):
            matrix.return_value.overview.return_value=self.project
            with self.assertRaises(JeevesAppwideError):
                runner.produce(self.root,self.out,local=True)
        self.assertFalse(self.out.exists())

    def test_failed_CI_claim_before_running_untrusted_tests(self):
        with (patch.dict(runner.os.environ,{"EXPECTED_SHA":self.sha,
                                            "CI":"false"},clear=True),
              patch.object(runner,"_commit",return_value=self.sha),
              patch.object(runner,"AppwideInventory") as inventory):
            with self.assertRaises(JeevesAppwideError):
                runner.produce(self.root,self.out,local=False)
            inventory.assert_not_called()

    def test_output_must_be_scoped_to_checked_out_workspace(self):
        def execute(argv,**kwargs):
            path=Path(next(x.split("=",1)[1] for x in argv
                           if x.startswith("--junitxml=")))
            path.write_text(xml(2))
            return CompletedProcess(argv,0,"2 passed","")
        with (patch.dict(runner.os.environ,{"EXPECTED_SHA":self.sha},clear=True),
              patch.object(runner,"_commit",return_value=self.sha),
              patch.object(runner,"AppwideInventory"),
              patch.object(runner,"JeevesAcceptanceTestMatrix") as matrix,
              patch.object(runner.subprocess,"run",side_effect=execute)):
            matrix.return_value.overview.return_value=self.project
            with TemporaryDirectory() as outside:
                with self.assertRaises(JeevesAppwideError):
                    runner.produce(self.root,Path(outside)/"bad.json",local=True)


if __name__ == "__main__":
    unittest.main()
