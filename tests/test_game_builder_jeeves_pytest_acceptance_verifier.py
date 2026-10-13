"""Same-head Windows/Linux pytest evidence: independent validation attacks."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import unittest

from skeleton.ai.game_builder.jeeves_appwide_fabric import JeevesAppwideError
from skeleton.ai.game_builder.jeeves_pytest_acceptance_verifier import verify_pytest


def stamp(report):
    report=deepcopy(report)
    report.pop("receipt_sha256", None)
    serial=json.dumps(report,sort_keys=True,separators=(",",":"),
                      ensure_ascii=False)
    report["receipt_sha256"]=sha256(serial.encode("utf-8")).hexdigest()
    return report


class IndependentlyVerifiedPytestTests(unittest.TestCase):
    def setUp(self):
        self.head="a"*40
        self.run_id=321654
        self.attempt=3
        self.modules=["tests.test_ai_webcrawler_advanced_admission",
                      "tests.test_ai_webcrawler_dragon_companion_runtime"]
        self.source=[
            {"path":name.replace(".","/")+".py","sha256":str(i+1)*64,
             "declared_test_case_count":3}
            for i,name in enumerate(self.modules)
        ]
        self.expected={
            "pytest_selected_modules":self.modules,
            "scheduled_pytest_module_count":2,
            "module_source_receipts":self.source,
            "matrix_sha256":"d"*64,
            "scope_sha256":"e"*64,
            "family_denominator":42,
            "pytest_smoke_families":[
                {"family_id":"F17","modules":[self.modules[0]]},
                {"family_id":"F18","modules":[self.modules[1]]},
            ],
        }
        self.run={
            "repository":{"full_name":"Apeloff1/Skeleton"},
            "id":self.run_id,"run_attempt":self.attempt,
            "head_sha":self.head,"name":"Jeeves App Pytest Acceptance",
            "event":"pull_request",
            "path":"Apeloff1/Skeleton/.github/workflows/jeeves-app-pytest-acceptance.yml@refs/pull/3747/merge",
            "status":"completed","conclusion":"success",
        }
        self.jobs=[]
        self.artifacts={}
        for osname,os_tag in (("Linux","ubuntu-24.04"),("Windows","windows-2022")):
            self.jobs.append({
                "id":501 if osname=="Linux" else 502,
                "name":"Selected source-bound pytest regressions ("+os_tag+")",
                "head_sha":self.head,"run_id":self.run_id,
                "run_attempt":self.attempt,"status":"completed",
                "conclusion":"success",
                "steps":[{"name":"Execute actual reviewed pytest family regressions",
                          "conclusion":"success"}],
            })
            results=[]
            for module in self.modules:
                results.append({
                    "module":module,
                    "command":["python","-m","pytest","-q",
                               "-p","no:cacheprovider","-o","addopts=",
                               module.replace(".","/")+".py"],
                    "started_utc":"2026-10-13T14:00:00+00:00",
                    "ended_utc":"2026-10-13T14:00:02+00:00",
                    "return_code":0,"timed_out":False,
                    "subprocess_executed":True,"pytest_cases_observed":2,
                    "junit_xml_sha256":"7"*64,
                    "targeted_tests_passed_in_runner":True,
                    "stdout":{"sha256":"8"*64,"total_bytes":12,
                              "content_stored_in_artifact":False},
                    "stderr":{"sha256":"9"*64,"total_bytes":0,
                              "content_stored_in_artifact":False},
                    "independent_ci_provenance_verified_by_this_script":False,
                })
            self.artifacts[osname]=stamp({
                "schema":"skeleton.ai.app_pytest_acceptance_run_evidence.v1",
                "git_head":self.head,"expected_head":self.head,"local_mode":False,
                "github_claims":{
                    "repository":"Apeloff1/Skeleton",
                    "run_id":str(self.run_id),"run_attempt":str(self.attempt),
                    "workflow":"Jeeves App Pytest Acceptance",
                    "os":osname,
                },
                "matrix_sha256":self.expected["matrix_sha256"],
                "scope_sha256":self.expected["scope_sha256"],
                "test_source_receipts":self.source,
                "pytest_family_count":2,"full_family_denominator":42,
                "candidate_modules":2,"modules_actually_executed":2,
                "modules_reporting_pass":2,"pytest_cases_observed_total":4,
                "selected_regression_suite_reported_success":True,
                "run_results":results,"release_device_verified":False,
                "user_journeys_verified":False,
                "full_app_completion_percent":None,
                "model_weight_promotion_performed":False,
            })

    def verify(self):
        return verify_pytest(
            head=self.head,run=self.run,jobs=self.jobs,
            evidence_by_os=self.artifacts,expected_matrix=self.expected,
            expected_run_id=self.run_id,expected_attempt=self.attempt)

    def test_two_independent_platforms_positive_cases_and_no_product_claim(self):
        result=self.verify()
        self.assertEqual(result["pytest_targeted_family_count"],2)
        self.assertEqual(result["pytest_targeted_family_subset_pct"],4.76)
        self.assertEqual(result["pytest_targeted_families"],["F17","F18"])
        self.assertEqual(result["verified_git_head"],self.head)
        self.assertTrue(result["independent_ci_execution_verified"])
        self.assertEqual([r["confirmed_executed_cases"]
                          for r in result["verified_os"]],[4,4])
        self.assertEqual(result["whole_feature_acceptance_admitted"],0)
        self.assertFalse(result["release_device_qualified"])
        self.assertIsNone(result["full_app_completion_percent"])
        self.assertEqual(result,self.verify())

    def test_partial_missing_or_false_Windows_job_never_qualifies(self):
        old=deepcopy(self.jobs)
        for action in (
            lambda: self.jobs.pop(),
            lambda: self.jobs[0].update(conclusion="failure"),
            lambda: self.jobs[1].update(head_sha="f"*40),
            lambda: self.jobs[0].update(steps=[]),
            lambda: self.jobs[1].update(run_attempt=1),
        ):
            self.jobs=deepcopy(old)
            action()
            with self.assertRaises(JeevesAppwideError):
                self.verify()
        self.jobs=old

    def test_unreviewed_family_and_malformed_denominator_rejected(self):
        for changed in (
            lambda: self.expected["pytest_smoke_families"].append(
                {"family_id":"F99","modules":[self.modules[0]]}),
            lambda: self.expected.update(family_denominator=40),
            lambda: self.expected["pytest_selected_modules"].append(
                "tests.test_unreviewed"),
            lambda: self.expected.update(matrix_sha256="no-sha"),
        ):
            old=deepcopy(self.expected)
            changed()
            with self.assertRaises(JeevesAppwideError):
                self.verify()
            self.expected=old

    def test_stale_or_replayed_git_ref_not_admitted(self):
        for field,alter in (
            ("head_sha","f"*40),
            ("run_attempt",1),
            ("conclusion","cancelled"),
            ("status","queued"),
            ("name","Unreviewed generator"),
            ("repository",{"full_name":"external/Skeleton"}),
        ):
            original=deepcopy(self.run[field])
            self.run[field]=alter
            with self.assertRaises(JeevesAppwideError):
                self.verify()
            self.run[field]=original

    def test_fake_report_counts_or_zero_pytest_test_cases_refused(self):
        old=deepcopy(self.artifacts["Linux"])
        for attack in (
            lambda x: x["run_results"][0].update(pytest_cases_observed=0),
            lambda x: x["run_results"][1].update(return_code=1),
            lambda x: x["run_results"][0].update(
                command=["python","-c","print('fake')"]),
            lambda x: x.update(pytest_cases_observed_total=0),
            lambda x: x.update(modules_reporting_pass=1),
            lambda x: x.update(full_app_completion_percent=100.0),
            lambda x: x["run_results"][1]["stderr"].update(
                content_stored_in_artifact=True),
        ):
            report=deepcopy(old)
            attack(report)
            self.artifacts["Linux"]=stamp(report)
            with self.assertRaises(JeevesAppwideError):
                self.verify()
        self.artifacts["Linux"]=old

    def test_modified_report_digest_and_cross_os_source_hash_mismatch(self):
        old=deepcopy(self.artifacts["Windows"])
        self.artifacts["Windows"]["modules_reporting_pass"]=0
        with self.assertRaises(JeevesAppwideError):
            self.verify()
        self.artifacts["Windows"]=deepcopy(old)
        report=deepcopy(old)
        report["test_source_receipts"][0]["sha256"]="f"*64
        self.artifacts["Windows"]=stamp(report)
        with self.assertRaises(JeevesAppwideError):
            self.verify()
        self.artifacts["Windows"]=old

    def test_live_GitHub_reader_uses_same_run_and_specific_pytest_artifact(self):
        from scripts.verify_app_acceptance_ci import GitHubEvidenceSource
        reader=GitHubEvidenceSource("read-only-test-token")
        reader.json=lambda path:self.run
        reader._page=lambda route,key:self.jobs if key=="jobs" else [
            {"id":11 if osname=="Linux" else 12,
             "name":"app-pytest-candidates-"+
                    ("ubuntu-24.04" if osname=="Linux" else "windows-2022")
                    +"-"+str(self.run_id),
             "expired":False,
             "workflow_run":{"id":self.run_id}}
            for osname in ("Linux","Windows")
        ]
        calls=[]
        def artifact(artifact_id, *, filename):
            calls.append((artifact_id,filename))
            return self.artifacts["Linux" if artifact_id==11 else "Windows"]
        reader.artifact=artifact
        run,jobs,evidence=reader.load(self.run_id,mode="pytest")
        self.assertEqual(run,self.run)
        self.assertEqual(jobs,self.jobs)
        self.assertEqual(len(evidence),2)
        self.assertEqual(
            calls,[(11,"app_pytest_acceptance_run_evidence.json"),
                   (12,"app_pytest_acceptance_run_evidence.json")])
        self.assertEqual(self.verify()["pytest_targeted_family_count"],2)

    def test_unsupported_artifact_mode_refused_before_any_network(self):
        from scripts.verify_app_acceptance_ci import GitHubEvidenceSource
        reader=GitHubEvidenceSource("read-only-test-token")
        with self.assertRaises(JeevesAppwideError):
            reader.load(self.run_id,mode="arbitrary-system-command")

    def test_missing_OS_artifact_fails_closed(self):
        self.artifacts.pop("Windows")
        with self.assertRaises(JeevesAppwideError):
            self.verify()


if __name__ == "__main__":
    unittest.main()
