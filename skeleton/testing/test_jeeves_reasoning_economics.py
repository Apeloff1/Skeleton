"""Tests of calibrated budget decisions, not simulated native performance."""
import unittest
from dataclasses import replace
from hashlib import sha256

from skeleton.ai.runtime.inference.reasoning_economics import (
    CalibrationScope, Observation, Stage, Limits, propose,
)


def pin(value):
    return sha256(value.encode()).hexdigest()


NOW=1000
SCOPE=CalibrationScope(*(pin(v) for v in ("model","runtime","tokenizer",
                     "profile","device","protocol")),thermal_band="warm")
LIMITS=Limits(4096,8192,1024,20000,8)


def stage(name,kind="answer",deps=(),required=True,value=5000):
    return Stage(pin(name),kind,tuple(pin(x) for x in deps),128,64,required,value)


def observations(kind,elapsed=1000,queue=100,success=True,
                 scope=SCOPE,at=NOW,n=5):
    return tuple(Observation(scope.identity,pin(kind+str(i)),kind,
                    128,64,128 if success else 0,64 if success else 0,
                    elapsed,queue,at,success) for i in range(n))


class ReasoningEconomicsTest(unittest.TestCase):
    def run_plan(self, stages, evidence, **kwargs):
        params=dict(scope=SCOPE,limits=LIMITS,now=NOW)
        params.update(kwargs)
        return propose(tuple(stages),evidence,**params)

    def test_dependency_required_even_if_marked_optional(self):
        a=stage("plan","plan",required=False)
        b=stage("answer",deps=("plan",))
        result=self.run_plan([b,a],observations("plan")+observations("answer"))
        self.assertTrue(result.ready)
        self.assertEqual(tuple(x.stage.stage_id for x in result.reservations),
                         (a.stage_id,b.stage_id))
        self.assertEqual(result.estimated_ms,2640)
        self.assertEqual(result.input_tokens,256)

    def test_required_failure_is_atomic(self):
        a=stage("plan","plan",required=False)
        b=stage("answer",deps=("plan",))
        result=self.run_plan([a,b],observations("answer"))
        self.assertFalse(result.ready)
        self.assertFalse(result.reservations)
        self.assertEqual(result.estimated_ms,0)
        self.assertIn("required:insufficient_calibration",dict(result.held).values())

    def test_optional_repair_skipped_under_remaining_budget(self):
        a=stage("answer")
        b=stage("repair","repair",deps=("answer",),required=False)
        evidence=observations("answer")+observations("repair",elapsed=18000)
        result=self.run_plan([a,b],evidence)
        self.assertTrue(result.ready)
        self.assertEqual(len(result.reservations),1)
        self.assertEqual(dict(result.held)[b.stage_id],"optional:aggregate_budget")

    def test_self_cycle_and_missing_dependency_reject(self):
        with self.assertRaises(ValueError):
            stage("a",deps=("a",))
        with self.assertRaises(ValueError):
            self.run_plan([stage("a",deps=("b",)),stage("b",deps=("a",))],[])
        with self.assertRaises(ValueError):
            self.run_plan([stage("a",deps=("absent",))],[])

    def test_identity_and_thermal_scope_not_transferable(self):
        other=replace(SCOPE,thermal_band="hot")
        result=self.run_plan([stage("answer")],observations("answer",scope=other))
        self.assertFalse(result.ready)

    def test_stale_and_future_observations_not_evidence(self):
        for at in (NOW-101,NOW+1):
            result=self.run_plan([stage("answer")],observations("answer",at=at),
                                 limits=replace(LIMITS,max_sample_age_seconds=100))
            self.assertFalse(result.ready)

    def test_failure_not_hidden_by_average(self):
        evidence=list(observations("answer"))
        evidence[-1]=replace(evidence[-1],success=False,actual_input_tokens=0,actual_output_tokens=0)
        result=self.run_plan([stage("answer")],evidence)
        self.assertEqual(dict(result.held).popitem()[1],"required:recorded_failure")

    def test_short_generation_is_not_full_shape_calibration(self):
        with self.assertRaises(ValueError):
            replace(observations("answer")[0],actual_output_tokens=1)

    def test_worst_latency_plus_margin_and_queue(self):
        evidence=list(observations("answer"))
        evidence[-1]=replace(evidence[-1],elapsed_ms=2000,queue_ms=500)
        result=self.run_plan([stage("answer")],evidence)
        self.assertEqual(result.estimated_ms,3000)

    def test_no_unmeasured_token_shape_extrapolation(self):
        a=replace(stage("answer"),output_ceiling=65)
        self.assertFalse(self.run_plan([a],observations("answer")).ready)

    def test_duplicate_trial_rejected(self):
        rows=observations("answer")
        with self.assertRaises(ValueError):
            self.run_plan([stage("answer")],rows+rows)

    def test_aggregate_token_limit_holds_mandatory(self):
        result=self.run_plan([stage("plan","plan"),stage("answer")],
                    observations("plan")+observations("answer"),
                    limits=replace(LIMITS,aggregate_input_tokens=128))
        self.assertFalse(result.ready)
        self.assertEqual(result.input_tokens,0)

    def test_optional_value_per_ms_prioritization(self):
        a=stage("answer")
        b=stage("verify","verify",required=False,value=8000)
        c=stage("repair","repair",required=False,value=3000)
        result=self.run_plan([a,b,c],observations("answer")+
                             observations("verify")+observations("repair"),
                             limits=replace(LIMITS,max_stages=2))
        self.assertEqual(tuple(x.stage.stage_id for x in result.reservations),
                         (a.stage_id,b.stage_id))

    def test_unknown_calibration_or_required_stage_empty(self):
        with self.assertRaises(ValueError):
            self.run_plan([stage("answer",required=False)],[])

    def test_deterministic_input_order(self):
        a=stage("plan","plan")
        b=stage("answer",deps=("plan",))
        evidence=observations("answer")+observations("plan")
        x=self.run_plan([a,b],evidence)
        y=self.run_plan([b,a],reversed(evidence))
        self.assertEqual(x.receipt_sha256,y.receipt_sha256)

    def test_nonfinite_numeric_fields(self):
        with self.assertRaises(ValueError):
            replace(LIMITS,available_ms=float("nan"))
        with self.assertRaises(ValueError):
            replace(observations("answer")[0],success=1)

    def test_negative_or_zero_budget_after_reserve_never_admits(self):
        result=self.run_plan([stage("answer")],observations("answer"),
                             limits=replace(LIMITS,available_ms=1))
        self.assertFalse(result.ready)


if __name__=="__main__":
    unittest.main()
