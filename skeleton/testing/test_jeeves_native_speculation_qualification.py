"""Source contracts for native speculative acceptance, no performance claims."""
import unittest
from hashlib import sha256
from dataclasses import replace
from skeleton.ai.runtime.inference.llama_cpp import LlamaCppConfig
from skeleton.ai.runtime.inference.measured_tuning import TuningScope,corpus_identity
from skeleton.ai.runtime.inference.native_speculation_qualification import (
    Pair,Trial,qualify,profile_identity,
)


def pin(s):
    return sha256(s.encode()).hexdigest()


CASES=(pin("a"),pin("b"))
SCOPE=TuningScope(pin("model"),pin("runtime"),pin("tokenizer"),pin("host"),
                  corpus_identity(CASES),pin("protocol"))
BASE=LlamaCppConfig(executable="llama",model_path="local.gguf",context_size=4096,
                    gpu_layers=0,temperature=0.0)
SPEC=replace(BASE,speculation_runtime_sha256=SCOPE.runtime_sha256,
             speculation_ngram=8,speculation_draft_tokens=16,
             speculation_min_hits=2,speculation_reserve_bytes=128*1024**2)


class NativeSpeculationQualification(unittest.TestCase):
    def setUp(self):
        self.pair=Pair(SCOPE,BASE,SPEC)

    def rows(self,config,*,elapsed=1000,output="exact",memory=512*1024**2,
             success=True,actual=12,finish="completed"):
        return [Trial(profile_identity(SCOPE,config),case,i,pin(output),finish,
                      128,16,actual,elapsed,memory,success)
                for case in CASES for i in range(3)]

    def choose(self,rows):
        return qualify(self.pair,rows,case_ids=CASES,host_limit=1024**3)

    def test_eligible_only_with_exact_and_faster_output(self):
        result=self.choose(self.rows(BASE)+self.rows(SPEC,elapsed=800))
        self.assertTrue(result.eligible)
        self.assertEqual(result.median_gain_bp,2000)

    def test_changed_token_sequence_even_same_length_rejected(self):
        result=self.choose(self.rows(BASE)+self.rows(SPEC,elapsed=800,output="different"))
        self.assertFalse(result.eligible)
        self.assertEqual(result.reason,"target_output_or_protocol_changed")

    def test_tail_regression(self):
        rows=self.rows(SPEC,elapsed=800)
        rows[-1]=replace(rows[-1],elapsed_us=2000)
        self.assertEqual(self.choose(self.rows(BASE)+rows).reason,"tail_latency_regression")

    def test_unqualified_memory_and_failure(self):
        for group in (self.rows(SPEC,elapsed=800,memory=2*1024**3),
                      self.rows(SPEC,success=False,actual=0,finish="error")):
            self.assertEqual(self.choose(self.rows(BASE)+group).reason,
                             "native_failure_or_capacity_hold")

    def test_missing_or_duplicate_trial(self):
        self.assertEqual(self.choose(self.rows(BASE)+self.rows(SPEC)[:-1]).reason,
                         "incomplete_pairs")
        rows=self.rows(BASE)
        with self.assertRaises(ValueError):
            self.choose(rows+[rows[0]])

    def test_unpinned_runtime_or_non_spec_drift(self):
        for config in (replace(SPEC,threads=2),
                       replace(SPEC,speculation_runtime_sha256=pin("other"))):
            with self.assertRaises(ValueError):
                Pair(SCOPE,BASE,config)

    def test_small_gain_no_activation(self):
        self.assertFalse(self.choose(self.rows(BASE)+self.rows(SPEC,elapsed=990)).eligible)

    def test_receipt_determinism(self):
        rows=self.rows(BASE)+self.rows(SPEC,elapsed=800)
        self.assertEqual(self.choose(rows).evidence_sha256,
                         self.choose(reversed(rows)).evidence_sha256)


if __name__=="__main__":
    unittest.main()
