"""Regression contracts for evidence-gated local tuning, no hardware claims."""
import unittest
from dataclasses import replace

from skeleton.ai.runtime.inference.llama_cpp import (
    ConsumerHardwareBudget, LlamaCppConfig, LlamaCppRuntimeError,
    plan_consumer_llama_cpp,
)
from skeleton.ai.runtime.inference.measured_tuning import (
    Candidate, Sample, TuningScope, candidates, corpus_identity, select,
)

MIB = 1024**2
GIB = 1024**3
CASES = ("a"*64, "b"*64)


class MeasuredTuningTests(unittest.TestCase):
    def setUp(self):
        self.config = LlamaCppConfig(
            executable="local-runtime", model_path="approved.gguf",
            context_size=8192, threads=8, batch_size=256,
            runtime_scratch_bytes=GIB, kv_bytes_per_token=128*1024,
            gpu_layers=0, kv_cache_type_k="f16", kv_cache_type_v="f16",
        )
        self.budget = ConsumerHardwareBudget(
            ram_bytes=8*GIB, physical_cpu_cores=8,
            kv_bytes_per_token=64*1024, target_context_tokens=4096,
            runtime_scratch_bytes=512*MIB,
        )
        self.scope = TuningScope("1"*64, "2"*64, "3"*64, "4"*64,
                                 corpus_identity(CASES), "5"*64)
        self.profiles = candidates(self.config, self.budget,
                                   model_bytes=2*GIB, scope=self.scope)
        self.baseline, self.trial = self.profiles[:2]

    def rows(self, candidate, *, total=10000, first=1200,
             quality=9800, peak=3*GIB, succeeded=True, output=16):
        return [Sample(candidate.identity, case, repeat, 128, output,
                       first, total, peak, quality, succeeded)
                for case in CASES for repeat in range(3)]

    def choose(self, rows, profiles=None, **kwargs):
        return select(profiles or (self.baseline, self.trial), rows,
                      case_ids=CASES, **kwargs)

    def test_planner_preserves_stronger_reserves_and_target(self):
        plan = self.baseline.plan
        self.assertEqual(plan.configuration.context_size, 4096)
        self.assertEqual(plan.configuration.runtime_scratch_bytes, GIB)
        self.assertEqual(plan.configuration.kv_bytes_per_token, 128*1024)
        self.assertEqual(plan.reserved_kv_bytes, 4096*128*1024)
        self.assertEqual(plan.estimated_total_bytes,
                         plan.reserved_ram_bytes + GIB + 2*GIB + plan.reserved_kv_bytes)
        self.assertTrue(plan.context_clamped)

    def test_smaller_budget_cannot_erase_existing_scratch(self):
        with self.assertRaises(LlamaCppRuntimeError):
            plan_consumer_llama_cpp(self.config,
                replace(self.budget, ram_bytes=3*GIB), model_bytes=2*GIB)

    def test_candidates_are_unique_and_do_not_change_context_or_quantization(self):
        self.assertLessEqual(len(self.profiles), 12)
        self.assertEqual(len({p.identity for p in self.profiles}), len(self.profiles))
        base = self.baseline.plan.configuration
        for p in self.profiles:
            c = p.plan.configuration
            self.assertEqual(replace(c, threads=base.threads, batch_size=base.batch_size), base)
            self.assertLessEqual(c.threads, base.threads)
            self.assertLessEqual(c.batch_size, base.batch_size)

    def test_selects_measured_quality_preserving_improvement(self):
        decision = self.choose(self.rows(self.baseline) + self.rows(self.trial,total=8000))
        self.assertEqual(decision.selected_sha256, self.trial.identity)
        self.assertEqual(decision.median_latency_gain_bp, 2000)
        self.assertEqual(decision.paired_trials, 6)
        self.assertTrue(decision.advisory_only)

    def test_missing_candidate_repeat_never_promotes(self):
        decision = self.choose(self.rows(self.baseline) + self.rows(self.trial,total=8000)[:-1])
        self.assertEqual(decision.selected_sha256, self.baseline.identity)

    def test_missing_baseline_prevents_promotion(self):
        decision = self.choose(self.rows(self.trial,total=8000))
        self.assertEqual(decision.reason, "baseline_unqualified_no_promotion")

    def test_slow_first_token_rejected(self):
        decision = self.choose(self.rows(self.baseline) + self.rows(self.trial,total=8000,first=2500))
        self.assertEqual(decision.selected_sha256, self.baseline.identity)

    def test_quality_regression_rejected_even_above_floor(self):
        decision = self.choose(self.rows(self.baseline) + self.rows(self.trial,total=8000,quality=9700))
        self.assertEqual(decision.selected_sha256, self.baseline.identity)

    def test_memory_excess_rejected(self):
        decision = self.choose(self.rows(self.baseline) + self.rows(self.trial,total=8000,peak=8*GIB))
        self.assertEqual(decision.selected_sha256, self.baseline.identity)

    def test_hidden_failed_trial_rejected(self):
        trial = self.rows(self.trial,total=8000)
        trial[-1] = replace(trial[-1], succeeded=False)
        decision = self.choose(self.rows(self.baseline) + trial)
        self.assertEqual(decision.selected_sha256, self.baseline.identity)

    def test_unmatched_output_lengths_rejected(self):
        decision = self.choose(self.rows(self.baseline) + self.rows(self.trial,total=8000,output=15))
        self.assertEqual(decision.selected_sha256, self.baseline.identity)

    def test_tail_regression_rejected(self):
        trial = self.rows(self.trial,total=8000)
        trial[-1] = replace(trial[-1], total_us=16000)
        self.assertEqual(self.choose(self.rows(self.baseline)+trial).selected_sha256,
                         self.baseline.identity)

    def test_duplicate_and_unknown_trial_are_invalid(self):
        rows = self.rows(self.baseline)
        with self.assertRaises(ValueError):
            self.choose(rows+[rows[0]])
        with self.assertRaises(ValueError):
            self.choose([replace(rows[0], candidate_sha256="f"*64)])

    def test_cross_host_evidence_not_comparable(self):
        other = Candidate(replace(self.scope, host_profile_sha256="f"*64),self.trial.plan)
        with self.assertRaises(ValueError):
            self.choose([], profiles=(self.baseline,other))

    def test_corpus_pin_and_nonfinite_sample_denied(self):
        with self.assertRaises(ValueError):
            select((self.baseline,self.trial), [],case_ids=("c"*64,))
        with self.assertRaises(ValueError):
            replace(self.rows(self.baseline)[0], total_us=float("nan"))
        with self.assertRaises(ValueError):
            replace(self.rows(self.baseline)[0], peak_bytes=True)

    def test_small_gain_does_not_switch(self):
        decision = self.choose(self.rows(self.baseline) + self.rows(self.trial,total=9900))
        self.assertEqual(decision.reason, "baseline_retained")


if __name__ == "__main__":
    unittest.main()
