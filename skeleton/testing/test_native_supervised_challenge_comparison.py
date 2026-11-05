"""A full candidate cannot hide regressions behind aggregate accuracy."""
from __future__ import annotations
from dataclasses import replace
import unittest
from skeleton.ai.runtime.operational_ai.native_supervised.challenge_catalog import iter_challenges
from skeleton.ai.runtime.operational_ai.native_supervised.challenge_runner import ChallengeRun
from skeleton.ai.runtime.operational_ai.native_supervised.challenge_executor import ProbeResult
from skeleton.ai.runtime.operational_ai.native_supervised.paired_comparison import compare
from skeleton.ai.runtime.operational_ai.native_supervised.challenge_score import score
from skeleton.ai.runtime.operational_ai.native_supervised.challenge_quality import qualify
from skeleton.ai.runtime.operational_ai.native_supervised.canonical import digest
from skeleton.ai.runtime.operational_ai.native_supervised.errors import SupervisedRejected


class TestNativeChallengeComparison(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases=tuple(iter_challenges())
        cls.source=digest([c.record() for c in cls.cases])

    def result(self,case,model,passed=True):
        return ProbeResult(
            case.case_id,case.domain,case.severity,case.sha256,
            case.prompt_sha256,case.expected_sha256,"f"*64,
            model,"c"*64,"d"*64,passed,1,16,8,"length",
        )

    def run(self,model,passed_ids=None,*,start=0,count=24):
        if passed_ids is None:
            passed_ids={x.case_id for x in self.cases}
        results=tuple(self.result(c,model,c.case_id in passed_ids)
                      for c in self.cases[start:start+count])
        return ChallengeRun(model,self.source,start,count,results)

    def test_no_self_comparison(self):
        x=self.run("a"*64)
        with self.assertRaises(SupervisedRejected):
            compare(x,x)

    def test_same_cases_required(self):
        champion=self.run("a"*64)
        contender=self.run("b"*64,start=24,count=24)
        with self.assertRaises(SupervisedRejected):
            compare(champion,contender)

    def test_partial_score_cannot_pass_full_suite(self):
        value=score(self.run("a"*64))
        self.assertEqual(value["total"],24)
        self.assertFalse(value["all_768_cases_measured"])
        self.assertFalse(value["challenge_quality_gate_met"])

    def test_positive_improvement_is_measured_not_accepted(self):
        cases=self.cases[:24]
        baseline={x.case_id for x in cases[1:]}
        challenger={x.case_id for x in cases}
        old=self.run("a"*64,baseline)
        new=self.run("b"*64,challenger)
        verdict=compare(old,new)
        self.assertEqual(verdict["improved"],1)
        self.assertFalse(verdict["full_768_case_comparison"])
        self.assertFalse(verdict["production_authorized"])
        self.assertEqual(qualify(old,new)["status"],"held-partial")

    def test_duplicate_case_results_rejected(self):
        run=self.run("a"*64)
        bad=list(run.results)
        bad[-1]=bad[0]
        corrupted=replace(run,results=tuple(bad))
        with self.assertRaises(SupervisedRejected):
            score(corrupted)

    def test_source_drift_rejected(self):
        first=self.run("a"*64)
        second=replace(self.run("b"*64),source_sha256="f"*64)
        with self.assertRaises(SupervisedRejected):
            compare(first,second)

    def test_forged_case_hash_rejected(self):
        run=self.run("a"*64)
        bad=list(run.results)
        bad[0]=replace(bad[0],case_sha256="0"*64)
        with self.assertRaises(SupervisedRejected):
            score(replace(run,results=tuple(bad)))


if __name__=="__main__":
    unittest.main()
