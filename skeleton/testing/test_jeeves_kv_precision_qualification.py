"""Independent source tests for measured KV precision qualification."""
import unittest
from hashlib import sha256
from dataclasses import replace

from skeleton.ai.runtime.inference.llama_cpp import GgufServingMetadata,LlamaCppConfig
from skeleton.ai.runtime.inference.measured_tuning import TuningScope,corpus_identity
from skeleton.ai.runtime.inference.kv_precision_qualification import (
    logical_kv_bytes,profiles,Trial,qualify,
)


def pin(s):
    return sha256(s.encode()).hexdigest()


CASES=(pin("critical"),pin("normal"))
META=GgufServingMetadata(architecture="llama",context_length=8192,
                         block_count=32,head_count=32,head_count_kv=8,
                         key_length=128,value_length=128)
CONFIG=LlamaCppConfig(executable="llama",model_path="local.gguf",context_size=4096,
                      gpu_layers=0,kv_cache_type_k="f16",kv_cache_type_v="f16",
                      kv_bytes_per_token=262144)
SCOPE=TuningScope(pin("model"),pin("runtime"),pin("tokenizer"),pin("host"),
                   corpus_identity(CASES),pin("protocol"))
MIB=1024**2


class KvPrecisionTests(unittest.TestCase):
    def setUp(self):
        self.profiles=profiles(CONFIG,META,scope=SCOPE,supported_pairs=(
            ("f16","f16"),("q8_0","q4_0"),("q8_0","q8_0")))
        self.base,self.trial,self.alt=self.profiles

    def rows(self,profile,*,host=800*MIB,device=0,elapsed=1000,quality=9900,
             success=True,critical="fixed",output=16):
        return [Trial(profile.identity,case,r,128,output,elapsed,host,device,
                      quality,success,pin(critical if case==CASES[0] else "normal"))
                for case in CASES for r in range(3)]

    def choose(self,rows,**kwargs):
        opts=dict(case_ids=CASES,critical_cases=frozenset(CASES[:1]),host_limit=1024*MIB)
        opts.update(kwargs)
        return qualify(self.profiles,rows,**opts)

    def test_block_storage_includes_scales(self):
        f=logical_kv_bytes(META,context=4096,key_type="f16",value_type="f16")
        q=logical_kv_bytes(META,context=4096,key_type="q8_0",value_type="q4_0")
        self.assertEqual(f,512*MIB)
        self.assertEqual(q,208*MIB)

    def test_non_aligned_rows_round_up(self):
        meta=replace(META,key_length=33,value_length=33)
        self.assertEqual(logical_kv_bytes(meta,context=128,key_type="q8_0",value_type="q4_0"),
                         128*32*8*(2*34+2*18))

    def test_unknown_geometry_refuses_estimate(self):
        for meta in (replace(META,architecture="deepseek2"),
                     replace(META,head_count_kv=None),replace(META,key_length=None)):
            with self.assertRaises(ValueError):
                logical_kv_bytes(meta,context=4096,key_type="f16",value_type="f16")

    def test_trained_context_ceiling(self):
        with self.assertRaises(ValueError):
            logical_kv_bytes(META,context=16384,key_type="f16",value_type="f16")

    def test_candidates_never_reduce_admission_reservations(self):
        for p in self.profiles:
            self.assertEqual(p.configuration.kv_bytes_per_token,CONFIG.kv_bytes_per_token)
            self.assertEqual(p.configuration.runtime_scratch_bytes,CONFIG.runtime_scratch_bytes)

    def test_selects_measured_memory_advantage(self):
        decision=self.choose(self.rows(self.base)+self.rows(self.trial,host=600*MIB))
        self.assertEqual(decision.recommended_sha256,self.trial.identity)
        self.assertIn(self.trial.identity,decision.retained)

    def test_logical_saving_alone_not_enough(self):
        decision=self.choose(self.rows(self.base)+self.rows(self.trial))
        self.assertEqual(decision.recommended_sha256,self.base.identity)

    def test_critical_output_change_rejected(self):
        decision=self.choose(self.rows(self.base)+self.rows(self.trial,host=600*MIB,critical="changed"))
        self.assertEqual(dict(decision.rejected)[self.trial.identity],"paired_regression")

    def test_quality_regression_rejected(self):
        decision=self.choose(self.rows(self.base)+self.rows(self.trial,host=600*MIB,quality=9800))
        self.assertEqual(decision.recommended_sha256,self.base.identity)

    def test_failure_and_missing_repeats_rejected(self):
        for trial in (self.rows(self.trial,host=600*MIB)[:-1],
                      self.rows(self.trial,host=600*MIB,success=False,output=0)):
            self.assertEqual(self.choose(self.rows(self.base)+trial).recommended_sha256,
                             self.base.identity)

    def test_no_baseline_no_recommendation(self):
        self.assertIsNone(self.choose(self.rows(self.trial)).recommended_sha256)

    def test_exact_token_shape(self):
        result=self.choose(self.rows(self.base)+self.rows(self.trial,host=600*MIB,output=15))
        self.assertEqual(result.recommended_sha256,self.base.identity)

    def test_latency_tail_blocks_candidate(self):
        samples=self.rows(self.trial,host=600*MIB)
        samples[-1]=replace(samples[-1],elapsed_us=2000)
        self.assertEqual(self.choose(self.rows(self.base)+samples).recommended_sha256,self.base.identity)

    def test_duplicate_trials_and_unknown_profiles_fail(self):
        b=self.rows(self.base)
        with self.assertRaises(ValueError):
            self.choose(b+[b[0]])
        with self.assertRaises(ValueError):
            self.choose([replace(b[0],profile_sha256=pin("unknown"))])

    def test_gpu_without_measured_bound_holds(self):
        gpu=profiles(replace(CONFIG,gpu_layers=2),META,scope=SCOPE,
                     supported_pairs=(("f16","f16"),("q8_0","q4_0")))
        with self.assertRaises(ValueError):
            qualify(gpu,[],case_ids=CASES,critical_cases=frozenset(CASES[:1]),
                    host_limit=1024*MIB)

    def test_pareto_does_not_discard_valid_tradeoffs(self):
        result=self.choose(self.rows(self.base)+self.rows(self.trial,host=600*MIB,elapsed=1050)
                          +self.rows(self.alt,host=700*MIB,elapsed=900))
        self.assertIn(self.trial.identity,result.retained)
        self.assertIn(self.alt.identity,result.retained)


if __name__=="__main__":
    unittest.main()
