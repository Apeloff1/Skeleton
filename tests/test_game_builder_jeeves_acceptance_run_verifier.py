"""Adversarial external-source CI acceptance test attestation contracts."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, patch
import zipfile

from skeleton.ai.game_builder.jeeves_appwide_fabric import JeevesAppwideError
from skeleton.ai.game_builder.jeeves_acceptance_run_verifier import verify
from scripts.verify_app_acceptance_ci import (
    GitHubEvidenceSource, _read_json, _unique_pairs,
)


class IndependentProductAcceptanceVerifierTests(unittest.TestCase):
    def setUp(self):
        self.commit="a"*40
        self.run_id=123456
        self.attempt=2
        self.modules=["tests.test_alpha","tests.test_beta"]
        self.expected={
            "selected_modules":self.modules,
            "module_source_receipts":[
                {"path":"tests/test_alpha.py","sha256":"b"*64,
                 "declared_test_case_count":2},
                {"path":"tests/test_beta.py","sha256":"c"*64,
                 "declared_test_case_count":4},
            ],
            "scheduled_test_module_count":2,
            "matrix_digest":"d"*64,
            "matrix_sha256":"e"*64,
            "scope_sha256":"f"*64,
        }
        self.run={
            "repository":{"full_name":"Apeloff1/Skeleton"},
            "id":self.run_id,
            "run_attempt":self.attempt,
            "name":"Jeeves App Acceptance Matrix",
            "event":"pull_request",
            "path":"Apeloff1/Skeleton/.github/workflows/jeeves-app-acceptance-matrix.yml@refs/pull/3747/merge",
            "head_sha":self.commit,
            "status":"completed",
            "conclusion":"success",
        }
        self.jobs=[]
        self.evidence={}
        for os_name,job_name in (
            ("Linux","Selected real product regressions (ubuntu-24.04)"),
            ("Windows","Selected real product regressions (windows-2022)"),
        ):
            self.jobs.append({
                "id":901 if os_name=="Linux" else 902,
                "run_id":self.run_id,"run_attempt":self.attempt,
                "head_sha":self.commit,
                "name":job_name,
                "status":"completed","conclusion":"success",
                "steps":[{"name":"Execute actual curated family regression suite",
                          "conclusion":"success"}],
            })
            result=[]
            for module in self.modules:
                result.append({
                    "module":module,
                    "command":["python","-m","unittest",module,"-q"],
                    "started_utc":"2026-10-13T11:00:00+00:00",
                    "ended_utc":"2026-10-13T11:00:01+00:00",
                    "unittest_cases_observed":2,
                    "return_code":0,"timed_out":False,
                    "subprocess_executed":True,
                    "targeted_tests_passed_in_runner":True,
                    "stdout":{"sha256":"0"*64,"total_bytes":0,
                              "content_stored_in_artifact":False},
                    "stderr":{"sha256":"0"*64,"total_bytes":0,
                              "content_stored_in_artifact":False},
                    "independent_ci_provenance_verified_by_this_script":False,
                })
            evidence={
                "schema":"skeleton.ai.app_acceptance_run_evidence.v1",
                "git_head":self.commit,
                "expected_head":self.commit,
                "local_mode":False,
                "github_claims":{
                    "repository":"Apeloff1/Skeleton",
                    "workflow":"Jeeves App Acceptance Matrix",
                    "run_id":str(self.run_id),"run_attempt":str(self.attempt),
                    "os":os_name,
                },
                "matrix_digest":self.expected["matrix_digest"],
                "matrix_sha256":self.expected["matrix_sha256"],
                "scope_sha256":self.expected["scope_sha256"],
                "test_source_receipts":self.expected["module_source_receipts"],
                "candidate_modules":2,"modules_actually_executed":2,
                "modules_reporting_pass":2,
                "total_unittest_cases_observed":4,
                "selected_regression_suite_reported_success":True,
                "run_results":result,
                "full_app_completion_percent":None,
                "release_device_verified":False,
                "user_journeys_verified":False,
                "model_weight_promotion_performed":False,
            }
            self.evidence[os_name]=self.stamp(evidence)

    @staticmethod
    def stamp(report):
        report=deepcopy(report)
        report.pop("receipt_sha256",None)
        data=json.dumps(report,sort_keys=True,separators=(",",":"),
                        ensure_ascii=False)
        report["receipt_sha256"]=sha256(data.encode("utf-8")).hexdigest()
        return report

    def check(self):
        return verify(
            head=self.commit,run=self.run,jobs=self.jobs,
            evidence_by_os=self.evidence,expected_matrix=self.expected,
            expected_run_id=self.run_id,expected_attempt=self.attempt)

    def test_both_operating_systems_verified_same_head_and_source(self):
        receipt=self.check()
        self.assertTrue(receipt["independent_ci_execution_verified"])
        self.assertEqual(receipt["verified_git_head"],self.commit)
        self.assertEqual(receipt["scheduled_test_modules_independently_confirmed"],2)
        self.assertEqual([x["observed_unittest_cases"] for x in receipt["verified_os"]],[4,4])
        self.assertEqual({i["os"] for i in receipt["verified_os"]},{"Linux","Windows"})
        self.assertIsNone(receipt["full_app_completion_percent"])
        self.assertFalse(receipt["release_device_qualified"])
        self.assertFalse(receipt["trained_model_quality_verified"])
        self.assertEqual(receipt,self.check())

    def test_OS_local_file_inventory_digest_may_differ_but_sources_must_agree(self):
        self.evidence["Windows"]["matrix_digest"]="1"*64
        self.evidence["Windows"]=self.stamp(self.evidence["Windows"])
        result=self.check()
        self.assertNotEqual(result["verified_os"][0]["matrix_digest_local_to_runner"],
                            result["verified_os"][1]["matrix_digest_local_to_runner"])
        self.evidence["Windows"]["matrix_sha256"]="2"*64
        self.evidence["Windows"]=self.stamp(self.evidence["Windows"])
        with self.assertRaises(JeevesAppwideError):
            self.check()

    def test_run_identity_attacks_fail_closed(self):
        for name,value in (
            ("head_sha","b"*40),("conclusion","cancelled"),
            ("status","queued"),("name","Other workflow"),
            ("event","schedule"),("path",".github/workflows/evil.yml"),
            ("run_attempt",1),("repository",{"full_name":"bad/Skeleton"}),
        ):
            old=deepcopy(self.run[name])
            self.run[name]=value
            with self.subTest(field=name),self.assertRaises(JeevesAppwideError):
                self.check()
            self.run[name]=old

    def test_OS_job_and_actual_test_step_proof_required(self):
        original=deepcopy(self.jobs)
        for alteration in (
            lambda: self.jobs.pop(),
            lambda: self.jobs[0].update(conclusion="failure"),
            lambda: self.jobs[1].update(head_sha="f"*40),
            lambda: self.jobs[0].update(steps=[]),
            lambda: self.jobs[0].update(name=self.jobs[1]["name"]),
        ):
            self.jobs=deepcopy(original)
            alteration()
            with self.assertRaises(JeevesAppwideError):
                self.check()
        self.jobs=original

    def test_both_artifacts_and_selected_module_identity_required(self):
        self.evidence.pop("Windows")
        with self.assertRaises(JeevesAppwideError):
            self.check()

    def test_false_test_success_or_missing_subprocess_never_counts(self):
        original=deepcopy(self.evidence["Linux"])
        for mutation in (
            lambda x: x.update(modules_reporting_pass=1),
            lambda x: x["run_results"][0].update(return_code=1),
            lambda x: x["run_results"][0].update(unittest_cases_observed=0),
            lambda x: x.update(total_unittest_cases_observed=0),
            lambda x: x["run_results"][0].update(subprocess_executed=False),
            lambda x: x["run_results"][1].update(module="tests.test_unreviewed"),
            lambda x: x.update(full_app_completion_percent=100.0),
            lambda x: x["run_results"][0].update(command=["sh","-c","anything"]),
            lambda x: x.update(user_journeys_verified=True),
        ):
            changed=deepcopy(original)
            mutation(changed)
            self.evidence["Linux"]=self.stamp(changed)
            with self.assertRaises(JeevesAppwideError):
                self.check()
        self.evidence["Linux"]=original

    def test_unsigned_artifact_edit_refused(self):
        self.evidence["Linux"]["candidate_modules"]=999
        with self.assertRaises(JeevesAppwideError):
            self.check()

    def test_UTF8_and_duplicate_json_trust_boundary(self):
        self.assertEqual(_read_json(b'{"a":1,"b":2}'),{"a":1,"b":2})
        for text in (b'{"a":1,"a":2}',
                     b'{"num":NaN}',b'{"x":Infinity}',
                     b'[INVALID]',b'\xff'):
            with self.subTest(text=text),self.assertRaises(JeevesAppwideError):
                _read_json(text)

    def test_artifact_zip_accepts_one_exact_safe_document(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/"artifact.zip"
            with zipfile.ZipFile(path,"w") as zipout:
                zipout.writestr("app_acceptance_run_evidence.json",
                                json.dumps(self.evidence["Linux"]))
            source=GitHubEvidenceSource("unit-test-placeholder-token")
            source._request=lambda _route,limit: path.read_bytes()
            report=source.artifact(987)
            self.assertEqual(report["github_claims"]["os"],"Linux")

    def test_artifact_zip_traversal_and_extra_files_rejected(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/"artifact.zip"
            source=GitHubEvidenceSource("unit-test-placeholder-token")
            source._request=lambda _route,limit: path.read_bytes()
            for name in ("../evidence.json", "other.json"):
                with zipfile.ZipFile(path,"w") as archive:
                    archive.writestr(name,"{}")
                with self.assertRaises(JeevesAppwideError):
                    source.artifact(987)
            with zipfile.ZipFile(path,"w") as archive:
                archive.writestr("app_acceptance_run_evidence.json","{}")
                archive.writestr("extra.txt","unexpected")
            with self.assertRaises(JeevesAppwideError):
                source.artifact(987)


if __name__ == "__main__":
    unittest.main()
