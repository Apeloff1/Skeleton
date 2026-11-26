"""Source-level checks for explicitly pinned native speculation; no model run."""
import tempfile
import unittest
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

from skeleton.ai.runtime.inference.llama_cpp import (
    LlamaCppConfig,LlamaCppModel,LlamaCppRuntimeError,GgufServingMetadata,
    ConsumerHardwareBudget,plan_consumer_llama_cpp,
)
from skeleton.ai.runtime.inference.local import LocalInferenceRequest
from skeleton.ai.runtime.inference.deployment import (
    create_local_model_deployment,LocalModelDeployment,LocalModelDeploymentError,
)

GIB=1024**3
MIB=1024**2
PIN="a"*64
BASE=LlamaCppConfig(executable="llama",model_path="local.gguf",context_size=4096,
                    gpu_layers=0,temperature=0.0)
SPEC=dict(speculation_runtime_sha256=PIN,speculation_ngram=8,
          speculation_draft_tokens=16,speculation_min_hits=2,
          speculation_reserve_bytes=128*MIB)


class NativeSpeculationConfigTests(unittest.TestCase):
    def fixture(self,config):
        obj=LlamaCppModel.__new__(LlamaCppModel)
        obj.config=config
        obj._runtime=SimpleNamespace(path="/approved/runtime",sha256=PIN)
        obj._model=SimpleNamespace(path="/approved/model",size_bytes=GIB)
        obj._serving_metadata=GgufServingMetadata(architecture="llama",context_length=4096)
        return obj

    def test_disabled_profile_no_flags(self):
        args=self.fixture(BASE)._command(Path("prompt"),LocalInferenceRequest("hi"))
        self.assertNotIn("--spec-type",args)

    def test_pinned_opt_in_builds_explicit_request_local_flags(self):
        args=self.fixture(replace(BASE,**SPEC))._command(Path("prompt"),
                  LocalInferenceRequest("hi",max_output_tokens=32))
        for flag,value in (("--spec-type","ngram-simple"),
                           ("--spec-ngram-simple-size-n","8"),
                           ("--spec-ngram-simple-size-m","16"),
                           ("--spec-ngram-simple-min-hits","2"),
                           ("--spec-draft-n-max","16")):
            self.assertEqual(args[args.index(flag)+1],value)
        self.assertNotIn("--model-draft",args)

    def test_runtime_identity_drift_holds(self):
        obj=self.fixture(replace(BASE,**SPEC))
        obj._runtime.sha256="b"*64
        with self.assertRaises(LlamaCppRuntimeError):
            obj._command(Path("prompt"),LocalInferenceRequest("hi"))

    def test_schema_generation_rejected(self):
        obj=self.fixture(replace(BASE,**SPEC))
        with self.assertRaises(LlamaCppRuntimeError):
            obj._command(Path("prompt"),LocalInferenceRequest("hi"),schema_file=Path("schema"))

    def test_budget_counts_extra_reserve(self):
        config=replace(BASE,**SPEC)
        budget=ConsumerHardwareBudget(8*GIB,8,65536,target_context_tokens=4096)
        base=plan_consumer_llama_cpp(BASE,budget,model_bytes=GIB)
        candidate=plan_consumer_llama_cpp(config,budget,model_bytes=GIB)
        self.assertEqual(candidate.estimated_total_bytes-base.estimated_total_bytes,128*MIB)
        req=LocalInferenceRequest("hi")
        self.assertEqual(self.fixture(config).estimate_memory_bytes(req)-
                         self.fixture(BASE).estimate_memory_bytes(req),128*MIB)

    def test_shape_and_greedy_requirements(self):
        for changes in ({"gpu_layers":1},{"temperature":0.1},
                        {"speculation_reserve_bytes":1},{"speculation_ngram":True},
                        {"speculation_draft_tokens":65},{"speculation_runtime_sha256":None}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                replace(BASE,**{**SPEC,**changes})
        with self.assertRaises(ValueError):
            replace(BASE,speculation_draft_tokens=4)

    def test_unmanaged_flags_cannot_enable_extra_model_or_cache(self):
        for args in (("--spec-type","draft-simple"),("--spec-default",),
                     ("--model-draft","other.gguf"),("-md","other.gguf"),
                     ("--hf-repo-draft","owner/name"),("--spec-draft-hf=x",),
                     ("--lookup-cache-dynamic","private.bin"),("-lcs=x",),
                     ("--spec-synth-len","5")):
            with self.subTest(args=args),self.assertRaises(ValueError):
                replace(BASE,extra_args=args)

    def test_documented_remote_and_unpinned_artifact_aliases_refused(self):
        for args in (("--docker-repo","remote"),("-dr=remote",),
                     ("--gpt-oss-20b-default",),("--vision-gemma-12b-default",),
                     ("--lora","unbound.gguf"),("--shard","other.gguf"),
                     ("--ple=other.gguf",),("--control-vector","extra.gguf"),
                     ("--prompt-cache","old.bin"),("--override-kv","x=str:y"),
                     ("--n-gpu-layers","all"),("--temperature","2"),
                     ("--draft-max","64"),("--device-draft","CPU")):
            with self.subTest(args=args),self.assertRaises(ValueError):
                replace(BASE,extra_args=args)

    def test_explicit_sampler_profile_reaches_native_command(self):
        model=self.fixture(BASE)
        args=model._command(Path("prompt"),LocalInferenceRequest(
            "hi",temperature=.7,top_k=17,top_p=.9,min_p=.03,repetition_penalty=1.15))
        for key,value in (("--temp","0.7"),("--top-k","17"),("--top-p","0.9"),
                          ("--min-p","0.03"),("--repeat-penalty","1.15")):
            self.assertEqual(args[args.index(key)+1],value)

    def test_default_sampler_preserves_deployment_options(self):
        model=self.fixture(replace(BASE,temperature=.35,extra_args=("--top-k","18")))
        args=model._command(Path("prompt"),LocalInferenceRequest("hi"))
        self.assertEqual(args[args.index("--temp")+1],"0.35")
        self.assertEqual(args.count("--top-k"),1)
        self.assertEqual(args[args.index("--top-k")+1],"18")

    def test_explicit_sampler_conflict_and_speculation_hold(self):
        model=self.fixture(replace(BASE,extra_args=("--top-k=18",)))
        with self.assertRaisesRegex(LlamaCppRuntimeError,"conflicts"):
            model._command(Path("prompt"),LocalInferenceRequest("hi",temperature=.5))
        spec=self.fixture(replace(BASE,**SPEC))
        with self.assertRaisesRegex(LlamaCppRuntimeError,"greedy"):
            spec._command(Path("prompt"),LocalInferenceRequest("hi",temperature=.5))

    def test_cli_top_k_integer_bound(self):
        with self.assertRaisesRegex(LlamaCppRuntimeError,"top_k"):
            self.fixture(BASE)._command(Path("prompt"),
                  LocalInferenceRequest("hi",top_k=2**31))

    def test_trained_context_is_independent_ceiling(self):
        obj=self.fixture(replace(BASE,**SPEC))
        obj._serving_metadata=GgufServingMetadata(architecture="llama",context_length=16)
        with self.assertRaises(LlamaCppRuntimeError):
            obj._command(Path("prompt"),LocalInferenceRequest("hi"))

if __name__=="__main__":
    unittest.main()
