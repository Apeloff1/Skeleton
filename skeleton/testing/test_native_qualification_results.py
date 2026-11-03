"""Result and report evidence never promote unverified model behavior."""
from __future__ import annotations
from dataclasses import replace
import unittest

from skeleton.ai.runtime.operational_ai.native_qualification.contracts import ModelIdentity
from skeleton.ai.runtime.operational_ai.native_qualification.report import QualificationReport
from skeleton.ai.runtime.operational_ai.native_qualification.results import StepResult, CaseResult
from skeleton.ai.runtime.operational_ai.native_qualification.policy import Threshold
from skeleton.ai.runtime.operational_ai.native_qualification.errors import QualificationError


def step(*, passed=True):
    return StepResult(
        0,"s_1","req_1",1,"a"*64,"b"*64,"c"*64,"d"*64,10,5,5,8,
        1 if passed else 0,1,() if passed else ("exact",),"recorded",False
    )


def report(*, real=False, complete=False, passed=True):
    result=CaseResult("case_1","arithmetic","high","e"*64,(step(passed=passed),),None)
    model=ModelIdentity("a"*64,"b"*64,"tenant","user","original","c"*64)
    return QualificationReport(
        "run_1",model,"d"*64,(result,), "2026-11-03T09:00Z","2026-11-03T09:01Z",
        real,real,complete,Threshold(minimum_total_percent=0,minimum_domain_percent=0),
    )


class TestQualificationResults(unittest.TestCase):
    def test_no_false_model_qualification_from_static_result(self):
        result=report(real=False,complete=True).record()
        self.assertFalse(result["policy_threshold_met"])
        self.assertFalse(result["release_certified"])

    def test_no_partial_corpus_promotion(self):
        self.assertFalse(report(real=True,complete=False).record()["policy_threshold_met"])

    def test_any_failed_case_denied_at_threshold(self):
        self.assertFalse(report(real=True,complete=True,passed=False).record()["policy_threshold_met"])

    def test_release_and_ci_holds_persist_with_perfect_score(self):
        result=report(real=True,complete=True).record()
        self.assertTrue(result["policy_threshold_met"])
        self.assertFalse(result["release_certified"])
        self.assertFalse(result["merge_certified"])
        self.assertFalse(result["ci_qualified"])

    def test_result_replay_not_new_generation(self):
        self.assertFalse(replace(step(), replayed=True).passed)

    def test_recovery_revision_and_check_count_consistency(self):
        with self.assertRaises(QualificationError):
            replace(step(),checks_total=2)


if __name__ == "__main__":
    unittest.main()
