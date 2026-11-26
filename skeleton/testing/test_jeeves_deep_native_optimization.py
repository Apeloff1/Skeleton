"""Executable native optimization regressions, without production-device claims."""
from __future__ import annotations

import math
import random
import unittest
from pathlib import Path
from unittest.mock import patch

from skeleton.cortex.attn import cached_mha, cached_mha_context, sample_logits, softmax
from skeleton.cortex.transformer import KVCache, TinyTransformer
from skeleton.ai.model_runtime.native_llm_runtime import NativeConversationSession, NativeLLMRuntime
from skeleton.ai.model_runtime.runtime_contracts import GenerationConfig, RuntimeContractError, RuntimeLimits


def old_sampler(logits, rng, *, temperature, top_k, top_p, min_p):
    """Independent original sorting/sampling trajectory for comparison."""
    n = len(logits)
    if temperature <= 1e-8 or top_k == 1:
        return max(range(n), key=lambda i: logits[i])
    maximum = max(logits)
    p = softmax([(x-maximum)/max(1e-6,temperature) for x in logits])
    if 0 < top_k < n:
        keep = set(sorted(range(n), key=lambda i:-p[i])[:top_k])
        p = [p[i] if i in keep else 0.0 for i in range(n)]
        total = sum(p) or 1.0
        p = [v/total for v in p]
    if min_p:
        floor = min_p * max(p)
        p = [v if v >= floor and v > 0.0 else 0.0 for v in p]
        total = sum(p)
        if total <= 0:
            return max(range(n),key=lambda i:logits[i])
        p = [v/total for v in p]
    if 0 < top_p < 1:
        order = sorted(range(n), key=lambda i:-p[i])
        acc = 0.0
        keep = set()
        for i in order:
            keep.add(i)
            acc += p[i]
            if acc >= top_p:
                break
        p = [p[i] if i in keep else 0.0 for i in range(n)]
        total = sum(p) or 1.0
        p = [v/total for v in p]
    r = rng.random()
    acc = 0.0
    fallback = max(i for i,v in enumerate(p) if v > 0.0)
    for i,v in enumerate(p):
        acc += v
        if v > 0 and r < acc:
            return i
    return fallback


def make_runtime(*, context=64, position="learned_rope", layers=2):
    return NativeLLMRuntime(TinyTransformer(
        vocab=("hello","world","local","code","answer","again","one","two","three"),
        dim=8, ctx=context, seed=41, n_heads=2, n_layers=layers,
        d_ff=8, position_mode=position,
    ))


class DeepNativeOptimizationTests(unittest.TestCase):
    def test_context_only_kernel_exact_head_parity(self):
        rng=random.Random(713)
        for width,heads in ((8,1),(8,2),(16,4),(12,3)):
            q=[rng.uniform(-1,1) for _ in range(width)]
            for length in (1,3,20,129):
                K=[[rng.uniform(-1,1) for _ in q] for _ in range(length)]
                V=[[rng.uniform(-1,1) for _ in q] for _ in range(length)]
                with self.subTest(width=width,heads=heads,length=length):
                    self.assertEqual(cached_mha_context(q,K,V,heads),
                                     cached_mha(q,K,V,heads)[0])

    def test_empty_and_malformed_attention_banks(self):
        self.assertEqual(cached_mha_context([1.,2.],[],[],2),[0.,0.])
        for q,K,V,h in (([1.],[[1.]],[],1),
                         ([1.,2.],[[1.]],[[1.,2.]],1),
                         ([1.,2.],[[1.,2.]],[[1.]],1),
                         ([1.,2.],[[1.,2.]],[[1.,2.]],3)):
            with self.subTest(q=q,K=K,V=V,h=h),self.assertRaises(ValueError):
                cached_mha_context(q,K,V,h)

    def test_cached_attention_cancellation_does_not_return_partial(self):
        calls=0
        def poll():
            nonlocal calls
            calls+=1
            if calls==5:
                raise RuntimeError("cancel")
        with self.assertRaisesRegex(RuntimeError,"cancel"):
            cached_mha_context([1.,2.,3.,4.],[[1.,2.,3.,4.]]*400,
                               [[1.,2.,3.,4.]]*400,2,interrupt=poll)

    def test_sampler_heap_exact_stable_ties_and_rng(self):
        logits=[float(i%13-6) if i%17 else -math.inf for i in range(1024)]
        for k in (2,8,31,128,256,0):
            for p in (0.25,0.9,1.0):
                for m in (0.,0.1,1.):
                    a,b=random.Random(42),random.Random(42)
                    config=dict(temperature=.73,top_k=k,top_p=p,min_p=m)
                    self.assertEqual([sample_logits(logits,a,**config) for _ in range(4)],
                                     [old_sampler(logits,b,**config) for _ in range(4)])
                    self.assertEqual(a.getstate(),b.getstate())

    def test_greedy_equal_ties_and_mask(self):
        self.assertEqual(sample_logits([-math.inf,2.,2.],random.Random(1),top_k=1),1)
        self.assertEqual(sample_logits([-math.inf,2.,2.],random.Random(1),temperature=0),1)

    def test_actual_cpu_decode_uses_new_context_kernel(self):
        runtime=make_runtime()
        original=cached_mha_context
        with patch("skeleton.cortex.transformer.cached_mha_context",wraps=original) as call:
            result=runtime.generate("hello world",GenerationConfig(max_new_tokens=2,temperature=0))
        self.assertEqual(len(result.generated_ids),2)
        self.assertGreater(call.call_count,0)

    def test_cache_and_reference_output_equivalence(self):
        for pos in ("learned_rope","rope"):
            for layers in (1,2):
                runtime=make_runtime(context=12,position=pos,layers=layers)
                cfg=dict(max_new_tokens=7,temperature=0)
                a=runtime.generate("hello world again one two three",GenerationConfig(**cfg,use_cache=True))
                b=runtime.generate("hello world again one two three",GenerationConfig(**cfg,use_cache=False))
                self.assertEqual(a.generated_ids,b.generated_ids)

    def test_teacher_forced_loss_matches_original_target_probability(self):
        runtime=make_runtime(context=10)
        model=runtime.model
        text="hello world again hello world again"
        ids=model._ids(text)
        for cached in (False,True):
            cache=KVCache(model.n_layers,model.ctx) if cached else None
            lp=0.0
            for i in range(1,len(ids)):
                window=ids[max(0,i-model.ctx):i]
                logits=model._logits_window(window,cache) if cached else model._logits(window)
                lp+=math.log(max(softmax(logits)[ids[i]],1e-12))
            self.assertEqual(model.logprob(text,cached=cached),lp/max(1,len(ids)-1))

    def test_loss_interrupt_inside_sample(self):
        model=make_runtime().model
        calls=0
        def poll():
            nonlocal calls
            calls+=1
            if calls>=4:
                raise TimeoutError("scoring deadline")
        with self.assertRaisesRegex(TimeoutError,"scoring deadline"):
            model.logprob("hello world again hello world again",interrupt=poll)

    def test_governed_mirror_bytes_match(self):
        root=Path(__file__).resolve().parents[2]
        for name in ("attn.py","transformer.py"):
            with self.subTest(file=name):
                self.assertEqual((root/"skeleton"/"cortex"/name).read_bytes(),
                                 (root/"skeleton"/"ai"/"runtime"/"cortex"/name).read_bytes())


class PrivatePrefixReuseTests(unittest.TestCase):
    def session(self, *, context=64, cap=4*1024**2, position="learned_rope"):
        return NativeConversationSession(make_runtime(context=context,position=position),
                                         prefix_cache_bytes=cap)

    def test_explicit_reuse_matches_cold_generation(self):
        a,b=self.session(),self.session(cap=0)
        cfg=GenerationConfig(max_new_tokens=3,temperature=.7,seed=19,top_k=4)
        for text in ("hello world","again local","one two"):
            x,y=a.generate(text,cfg),b.generate(text,cfg)
            self.assertEqual(x.generated_ids,y.generated_ids)
            self.assertEqual(x.output_digest,y.output_digest)
            self.assertEqual(x.usage.generated_tokens,y.usage.generated_tokens)
            self.assertEqual(a.token_ids,b.token_ids)
        self.assertGreater(a.prefix_cache_status["previous_turn_prefix_tokens"],0)
        self.assertLessEqual(a.prefix_cache_status["estimated_retained_python_bytes"],
                             a.prefix_cache_status["retention_budget_bytes"])
        self.assertEqual(b.prefix_cache_status["retained_tokens"],0)

    def test_reset_and_fork_do_not_copy_prefix_bank(self):
        s=self.session()
        s.generate("hello world",GenerationConfig(max_new_tokens=2,temperature=0))
        self.assertGreater(s.prefix_cache_status["retained_tokens"],0)
        child=s.fork()
        self.assertEqual(child.token_ids,s.token_ids)
        self.assertEqual(child.prefix_cache_status["retained_tokens"],0)
        s.reset()
        self.assertFalse(s.token_ids)
        self.assertEqual(s.prefix_cache_status["retained_tokens"],0)

    def test_tiny_retention_budget_discards_bank(self):
        s=self.session(cap=1)
        s.generate("hello world",GenerationConfig(max_new_tokens=2,temperature=0))
        self.assertEqual(s.prefix_cache_status["retained_tokens"],0)

    def test_history_mutations_clear_bank(self):
        cfg=GenerationConfig(max_new_tokens=2,temperature=0)
        for mutate in (lambda s:s.append_text("again"),lambda s:s.truncate(2),
                       lambda s:s.drop_prefix(1),lambda s:s.replace_history(s.token_ids)):
            s=self.session()
            s.generate("hello world",cfg)
            self.assertGreater(s.prefix_cache_status["retained_tokens"],0)
            mutate(s)
            self.assertEqual(s.prefix_cache_status["retained_tokens"],0)

    def test_no_cache_configuration_clears_previous_bank(self):
        s=self.session()
        s.generate("hello world",GenerationConfig(max_new_tokens=2,temperature=0))
        s.generate("again",GenerationConfig(max_new_tokens=2,temperature=0,use_cache=False))
        self.assertEqual(s.prefix_cache_status["retained_tokens"],0)

    def test_failure_cannot_commit_partial_prefix_or_history(self):
        s=self.session()
        cfg=GenerationConfig(max_new_tokens=2,temperature=0)
        s.generate("hello world",cfg)
        history=s.token_ids
        with patch.object(s.runtime.model,"_logits_window",side_effect=RuntimeError("fixture failure")):
            with self.assertRaisesRegex(RuntimeError,"fixture failure"):
                s.generate("again",cfg)
        self.assertEqual(s.token_ids,history)
        self.assertEqual(s.prefix_cache_status["retained_tokens"],0)

    def test_window_shift_does_not_publish_wrong_prefix(self):
        a,b=self.session(context=8,position="rope"),self.session(context=8,position="rope",cap=0)
        cfg=GenerationConfig(max_new_tokens=4,temperature=0)
        for text in ("hello world again one","two three","hello"):
            x,y=a.generate(text,cfg),b.generate(text,cfg)
            self.assertEqual(x.generated_ids,y.generated_ids)
            self.assertEqual(a.token_ids,b.token_ids)

    def test_idle_prefix_retention_is_shared_and_bounded_across_sessions(self):
        model=TinyTransformer(vocab=("hello","world","again"),dim=8,ctx=32,
                              seed=41,n_heads=2,n_layers=2,d_ff=8)
        runtime=NativeLLMRuntime(model,limits=RuntimeLimits(
            max_context=32,max_new_tokens=8,max_total_tokens=40,max_kv_bytes=16384))
        sessions=[NativeConversationSession(runtime,prefix_cache_bytes=16384) for _ in range(8)]
        cfg=GenerationConfig(max_new_tokens=3,temperature=0)
        for session in sessions:
            session.generate("hello world again",cfg)
        sizes=[x.prefix_cache_status["estimated_retained_python_bytes"] for x in sessions]
        self.assertGreater(sum(sizes),0)
        self.assertLessEqual(sum(sizes),16384)
        self.assertIn(0,sizes)
        for session in sessions:
            session.reset()
        self.assertFalse(runtime._idle_prefix_bytes)

    def test_prefix_budget_validated(self):
        r=make_runtime()
        for cap in (-1,True,10**12):
            with self.assertRaises(RuntimeContractError):
                NativeConversationSession(r,prefix_cache_bytes=cap)


if __name__=="__main__":
    unittest.main()
