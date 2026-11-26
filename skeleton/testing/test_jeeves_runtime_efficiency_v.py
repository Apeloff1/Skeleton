"""Phase V runtime regressions, including actual CPU SGD and decoding."""
from __future__ import annotations

import random
import unittest
import threading
from hashlib import sha256
from unittest.mock import patch
from dataclasses import replace

from skeleton.cortex.transformer import TinyTransformer
from skeleton.cortex.attn import cosine_lr
from skeleton.ai.model_runtime import NativeLLMRuntime
from skeleton.ai.model_runtime.flgb_model_runtime import canonical_bytes
from skeleton.ai.model_runtime.runtime_checkpoint import (
    _canonical_digest_and_size, _digest_and_size, portable_model_snapshot,
    snapshot_digest, validate_checkpoint,
)
from skeleton.ai.runtime.inference.native_runtime import NativeRuntimeLocalModel
from skeleton.ai.runtime.inference.local import LocalInferenceRequest

def make_model():
    return TinyTransformer(vocab=("user","assistant","alpha","beta","gamma","delta","hello"),
                           dim=8,ctx=8,n_layers=2,n_heads=2,d_ff=8,seed=11)

class StreamedSGDTests(unittest.TestCase):
    def test_exact_legacy_optimizer_trajectory(self):
        for schedule in ("const","cosine"):
            a,b=make_model(),make_model()
            corpus=("alpha beta gamma delta","hello alpha","alpha","")
            active=[x for x in corpus if x]
            windows=[]
            for text in active:
                ids=a._ids(text)
                for i in range(1,len(ids)):
                    windows.append((ids[max(0,i-a.ctx):i],ids[i]))
            for step,(window,target) in enumerate(windows):
                lr=cosine_lr(step,max(1,len(windows)),base=.025) if schedule=="cosine" else .025
                a._sgd(window,target,lr)
            a.fitted+=len(active)
            self.assertEqual(b.fit(iter(corpus),lr=.025,schedule=schedule),len(windows))
            self.assertEqual(snapshot_digest(portable_model_snapshot(a)),
                             snapshot_digest(portable_model_snapshot(b)))

    def test_interrupt_before_optimizer_mutation(self):
        model=make_model()
        before=snapshot_digest(portable_model_snapshot(model))
        def stop(): raise TimeoutError("preempt")
        with self.assertRaises(TimeoutError):
            model.fit(("alpha beta gamma",),interrupt=stop)
        self.assertEqual(snapshot_digest(portable_model_snapshot(model)),before)

    def test_interrupt_after_one_optimizer_step(self):
        model=make_model()
        def stop():
            if model.steps: raise TimeoutError("preempt")
        with self.assertRaises(TimeoutError):
            model.fit(("alpha beta gamma delta",),interrupt=stop)
        self.assertEqual(model.steps,1)

    def test_tokenizer_runs_once_before_each_sample_training(self):
        model=make_model()
        with patch.object(model,"_ids",wraps=model._ids) as call:
            model.fit(("alpha beta gamma","hello alpha"))
        self.assertEqual(call.call_count,2)

class CheckpointStreamingTests(unittest.TestCase):
    def test_canonical_utf8_and_float_identity(self):
        value={"z":[-0.0,1e-19,1e30,2,True,None],"a":{"日本語":"räksmörgås","x":['"','\\n']}}
        raw=canonical_bytes(value)
        self.assertEqual(_canonical_digest_and_size(value),(sha256(raw).hexdigest(),len(raw)))

    def test_byte_budget_rejects_before_success(self):
        value={"large":"å"*65000}
        raw=canonical_bytes(value)
        self.assertEqual(_canonical_digest_and_size(value,maximum=len(raw))[1],len(raw))
        with self.assertRaises(ValueError):
            _canonical_digest_and_size(value,maximum=len(raw)-1)

    def test_real_large_weight_shape_selects_streaming_and_preserves_digest(self):
        model=TinyTransformer(vocab=("alpha","beta","gamma"),dim=128,ctx=32,n_layers=2,n_heads=8,d_ff=128,seed=3)
        snapshot=portable_model_snapshot(model)
        raw=canonical_bytes(snapshot)
        self.assertEqual(_digest_and_size(snapshot),(sha256(raw).hexdigest(),len(raw)))
        self.assertEqual(snapshot_digest(snapshot),sha256(raw).hexdigest())

    def test_nonfinite_and_unsupported_values_fail(self):
        for value in ({"x":float("inf")},{"x":float("nan")},{"x":object()}):
            with self.subTest(value=value),self.assertRaises(ValueError):
                _canonical_digest_and_size(value)

    def test_runtime_checkpoint_round_trip(self):
        source=NativeLLMRuntime(make_model())
        cp=source.checkpoint()
        validated=validate_checkpoint(cp)
        self.assertEqual(validated["model_digest"],source.model_digest)
        restored=NativeLLMRuntime.restore(cp)
        self.assertEqual(source.model_digest,restored.model_digest)

class NativeRequestSamplingTests(unittest.TestCase):
    def test_actual_adapter_forwards_effective_profile(self):
        runtime=NativeLLMRuntime(TinyTransformer(vocab=("user","assistant","alpha","beta","gamma","delta","hello"),
                                                   dim=8,ctx=64,n_layers=2,n_heads=2,d_ff=8,seed=11))
        adapter=NativeRuntimeLocalModel(runtime)
        req=LocalInferenceRequest("alpha",max_output_tokens=3,seed=19,temperature=.6,
                                  top_k=3,top_p=.9,min_p=.05,repetition_penalty=1.1)
        with patch.object(runtime,"stream_sequence",wraps=runtime.stream_sequence) as stream:
            adapter.infer(req,threading.Event())
            config=stream.call_args.args[1]
            self.assertEqual((config.temperature,config.top_k,config.top_p,config.min_p,config.repetition_penalty),
                             (.6,3,.9,.05,1.1))

    def test_legacy_default_is_greedy_and_explicit_zero_supported(self):
        runtime=NativeLLMRuntime(TinyTransformer(vocab=("user","assistant","alpha","beta","gamma","delta","hello"),
                                                   dim=8,ctx=64,n_layers=2,n_heads=2,d_ff=8,seed=11))
        adapter=NativeRuntimeLocalModel(runtime)
        for kwargs in ({},{"temperature":0.0}):
            with patch.object(runtime,"stream_sequence",wraps=runtime.stream_sequence) as stream:
                adapter.infer(LocalInferenceRequest("alpha",max_output_tokens=2,**kwargs),threading.Event())
                self.assertEqual(stream.call_args.args[1].temperature,0.0)

    def test_top_k_outside_vocabulary_rejected(self):
        adapter=NativeRuntimeLocalModel(NativeLLMRuntime(TinyTransformer(
            vocab=("user","assistant","alpha","beta"),dim=8,ctx=64)))
        with self.assertRaisesRegex(RuntimeError,"top_k"):
            adapter.infer(LocalInferenceRequest("alpha",max_output_tokens=2,top_k=100000),threading.Event())

if __name__=="__main__":
    unittest.main()
