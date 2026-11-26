"""Exact compute-equivalence regressions for the real reference native runtime."""
from __future__ import annotations

from collections import Counter
from dataclasses import replace
import math
import random
import unittest
from unittest.mock import patch

from skeleton.cortex.bpe import BytePairEncoder, _apply, _chars, _encode_indexed
from skeleton.cortex.attn import apply_rope, apply_rope_bwd, _rope_phase_table, sample_logits, softmax
from skeleton.cortex.transformer import TinyTransformer
from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.model_runtime.runtime_contracts import BatchGenerationRequest, GenerationConfig, RuntimeContractError
from skeleton.ai.model_runtime.decode_acceleration import RollingPenaltyWindow, WordStopMatcher


def legacy_encode(text, merges):
    stream = list(_chars(text))
    for a, b, m in merges:
        stream = _apply(stream, (a, b), m)
    return tuple(stream)


def dense_sample(logits, rng, *, temperature=1., top_k=0, top_p=1., min_p=0.):
    n=len(logits)
    if temperature <= 1e-8 or top_k==1:
        return max(range(n), key=lambda i:logits[i])
    t=max(1e-6,temperature)
    maximum=max(logits)
    p=softmax([(x-maximum)/t for x in logits])
    if 0<top_k<n:
        keep=set(sorted(range(n),key=lambda i:-p[i])[:top_k])
        p=[p[i] if i in keep else 0. for i in range(n)]
        s=sum(p) or 1.
        p=[x/s for x in p]
    if min_p>0:
        floor=min_p*max(p)
        p=[x if x>=floor and x>0. else 0. for x in p]
        total=sum(p)
        if total<=0:
            return max(range(n),key=lambda i:logits[i])
        p=[x/total for x in p]
    if 0<top_p<1:
        acc=0.;keep=set()
        for i in sorted(range(n),key=lambda i:-p[i]):
            keep.add(i);acc+=p[i]
            if acc>=top_p:break
        p=[p[i] if i in keep else 0. for i in range(n)]
        s=sum(p) or 1.
        p=[x/s for x in p]
    if rng is None:return max(range(n),key=lambda i:p[i])
    r=rng.random();acc=0.;nxt=max(i for i,v in enumerate(p) if v>0.)
    for i,pv in enumerate(p):
        acc+=pv
        if pv>0. and r<acc:
            return i
    return nxt


class IndexedTokenizerTests(unittest.TestCase):
    def test_fitted_tokenizer_exact_on_original_and_unseen_corpora(self):
        enc=BytePairEncoder(merges=96)
        enc.fit(["game shader mesh procedural rendering alpha beta "*100,
                 "animation texture lighting physics combat "*80,
                 "rasterizer shadows particle systems procedural generation "*90])
        self.assertGreaterEqual(len(enc.merges),16)
        for text in ("game shader mesh "*100, "PROCEDURAL animation "*50,
                     "blåbær unicode Ω 日本語 "*40, "a"*300, "unseen " * 50, ""):
            self.assertEqual(enc.encode_pieces(text),legacy_encode(text,enc.merges))

    def test_overlaps_and_new_same_rule_edges_are_not_consumed(self):
        for text,merges in (
            ("aaaaaaa",[("a","a","a"),("a","a","aa")]),
            ("aaaaaaa",[("a","a","aa"),("aa","a","aaa"),("aa","aa","aaaa")]),
            ("ababab",[("a","b","b"),("b","b","b"),("b","b","bb")]),
            ("abbaabba",[("a","b","a"),("b","a","b"),("a","b","a")]),
        ):
            self.assertEqual(_encode_indexed(_chars(text),merges),legacy_encode(text,merges))

    def test_random_restored_rule_lists_preserve_sequential_wave_order(self):
        rng=random.Random(123)
        alphabet=["a","b","c","ab","ba","aa","bb","ac","x"]
        for _ in range(150):
            text="".join(rng.choice("abc") for _ in range(200))
            merges=[tuple(rng.choice(alphabet) for _ in range(3)) for _ in range(48)]
            self.assertEqual(_encode_indexed(_chars(text),merges),legacy_encode(text,merges))

    def test_long_input_uses_indexed_path_without_per_rule_full_scan(self):
        enc=BytePairEncoder()
        enc.merges=[("a","b","ab")]+[("q","q","qq")]*30
        text="ab"*1000
        with patch("skeleton.cortex.bpe._apply",side_effect=AssertionError("legacy sweep")):
            self.assertEqual(enc.encode_pieces(text),("ab",)*1000)

    def test_short_input_retains_legacy_fallback(self):
        enc=BytePairEncoder()
        enc.merges=[("a","b","ab")]*20
        with patch("skeleton.cortex.bpe._encode_indexed",side_effect=AssertionError("unexpected index")):
            self.assertEqual(enc.encode_pieces("ab"),("ab",))


class SamplerAndRotaryTests(unittest.TestCase):
    def test_sparse_sampler_exact_seeded_dense_equivalence(self):
        rng=random.Random(19)
        cases=(
            [float(i%5) for i in range(300)],
            [float("-inf") if i%3 else i*.01 for i in range(300)],
            [1000.,0.,-1000.]+[-10000.]*297,
            [rng.uniform(-40,40) for _ in range(300)],
        )
        for logits in cases:
            for k in (2,5,17):
                for top_p in (.01,.45,.99,1.):
                    for min_p in (0.,.02,.99,1.):
                        for seed in (0,31,71):
                            kwargs=dict(temperature=.7,top_k=k,top_p=top_p,min_p=min_p)
                            a,b=random.Random(seed),random.Random(seed)
                            self.assertEqual(sample_logits(logits,a,**kwargs),
                                             dense_sample(logits,b,**kwargs))
                            self.assertEqual(a.getstate(),b.getstate())

    def test_sparse_deterministic_argmax_stable_ties(self):
        logits=[0.]*256
        self.assertEqual(sample_logits(logits,None,top_k=8,top_p=.9),0)
        self.assertEqual(sample_logits(logits,random.Random(0),top_k=8,min_p=1.),
                         dense_sample(logits,random.Random(0),top_k=8,min_p=1.))

    def test_rotary_cached_geometry_is_exact_and_bounded(self):
        _rope_phase_table.cache_clear()
        values=[.13,-.21,.33,.77,-.5,1.4,.65]
        def reference(x,pos,base):
            out=list(x)
            d=max(2,len(x)-(len(x)%2))
            for i in range(0,d,2):
                theta=float(pos)/(base**(i/float(d)))
                c,s=math.cos(theta),math.sin(theta)
                a,b=out[i],out[i+1]
                out[i]=a*c-b*s;out[i+1]=a*s+b*c
            return out
        for p in (-3,0,1,41):
            self.assertEqual(apply_rope(values,p),reference(values,p,10000.))
            self.assertEqual(apply_rope_bwd(values,p),reference(values,-p,10000.))
            self.assertEqual(apply_rope(values,p,base=5000.),reference(values,p,5000.))
        a=_rope_phase_table.cache_info()
        apply_rope(values,41);apply_rope(values,41)
        self.assertGreaterEqual(_rope_phase_table.cache_info().hits,a.hits+2)
        for p in range(300):
            apply_rope(values,p)
        self.assertLessEqual(_rope_phase_table.cache_info().currsize,128)


def make_runtime(ctx=64):
    return NativeLLMRuntime(TinyTransformer(
        vocab=("alpha","beta","gamma","delta","hello","world","render","mesh",
               "shader","texture","code","test"),dim=8,ctx=ctx,n_heads=2,n_layers=2,d_ff=8,seed=73))


class BatchReuseTests(unittest.TestCase):
    def requests(self):
        config=GenerationConfig(max_new_tokens=3,temperature=.65,seed=23,top_k=4)
        return (
            BatchGenerationRequest("request-1","alpha beta gamma delta mesh",config),
            BatchGenerationRequest("request-2","hello world texture",replace(config,seed=17)),
            BatchGenerationRequest("request-3","alpha beta gamma delta code",replace(config,seed=8)),
            BatchGenerationRequest("request-4","alpha beta gamma delta shader",config),
            BatchGenerationRequest("request-5","alpha beta gamma delta shader",replace(config,seed=11)),
        )

    def test_actual_graph_step_reduction_and_seeded_receipt_parity(self):
        runtime=make_runtime()
        requests=self.requests()
        with patch.object(runtime.model,"_step",wraps=runtime.model._step) as steps:
            cold=runtime.generate_batch(requests)
            base=steps.call_count
        with patch.object(runtime.model,"_step",wraps=runtime.model._step) as steps:
            warm=runtime.generate_batch(requests,reuse_shared_prefix=True)
            optimized=steps.call_count
        self.assertLess(optimized,base)
        self.assertEqual([x.request_id for x in warm],[r.request_id for r in requests])
        for a,b in zip(cold,warm):
            self.assertEqual(a.result.generated_ids,b.result.generated_ids)
            self.assertEqual(a.result.text,b.result.text)
            self.assertEqual(a.result.replay_receipt,b.result.replay_receipt)
            self.assertEqual(a.result.checkpoint_digest,b.result.checkpoint_digest)

    def test_budget_too_small_falls_back_without_receipt_change(self):
        runtime=make_runtime()
        requests=self.requests()
        with patch.object(runtime.model,"_step",wraps=runtime.model._step) as steps:
            cold=runtime.generate_batch(requests)
            base=steps.call_count
        with patch.object(runtime.model,"_step",wraps=runtime.model._step) as steps:
            warm=runtime.generate_batch(requests,reuse_shared_prefix=True,prefix_budget_bytes=1)
            self.assertEqual(steps.call_count,base)
        self.assertEqual([x.result.replay_receipt for x in cold],[x.result.replay_receipt for x in warm])

    def test_cache_disabled_request_and_sliding_windows_preserve_outputs(self):
        runtime=make_runtime(8)
        requests=self.requests()
        requests=requests[:1]+(replace(requests[1],config=replace(requests[1].config,use_cache=False)),)
        cold=runtime.generate_batch(requests)
        warm=runtime.generate_batch(requests,reuse_shared_prefix=True)
        self.assertEqual([x.result.replay_receipt for x in cold],[x.result.replay_receipt for x in warm])
        requests=tuple(BatchGenerationRequest("slide-"+str(i),"alpha beta gamma delta mesh code",
                         GenerationConfig(max_new_tokens=4,seed=i)) for i in range(2))
        cold=runtime.generate_batch(requests)
        warm=runtime.generate_batch(requests,reuse_shared_prefix=True)
        self.assertEqual([x.result.replay_receipt for x in cold],[x.result.replay_receipt for x in warm])

    def test_batch_uses_no_retained_prefix_across_calls(self):
        runtime=make_runtime()
        requests=self.requests()
        counts=[]
        for _ in range(2):
            with patch.object(runtime.model,"_step",wraps=runtime.model._step) as steps:
                runtime.generate_batch(requests,reuse_shared_prefix=True)
                counts.append(steps.call_count)
        self.assertEqual(counts[0],counts[1])

    def test_bad_shared_policy_and_duplicate_rejected_before_work(self):
        runtime=make_runtime()
        with patch.object(runtime.model,"_step",side_effect=AssertionError("unadmitted work")):
            for opts in ({"reuse_shared_prefix":1},{"prefix_budget_bytes":0},
                         {"prefix_budget_bytes":True}):
                with self.assertRaises(RuntimeContractError):
                    runtime.generate_batch(self.requests(),**opts)
            with self.assertRaises(RuntimeContractError):
                runtime.generate_batch((self.requests()[0],)*2,reuse_shared_prefix=True)


class DecodeAuxiliaryTests(unittest.TestCase):
    def test_rolling_window_matches_full_counter_at_every_eviction(self):
        rng=random.Random(44)
        history=[rng.randrange(11) for _ in range(70)]
        for width in (1,3,64,100):
            sequence=history[:]
            window=RollingPenaltyWindow(sequence,width)
            for _ in range(100):
                self.assertEqual(window.counts,Counter(sequence[-width:]))
                tok=rng.randrange(11)
                sequence.append(tok);window.append(tok)

    def test_rolling_penalty_adjustment_is_exact_for_real_logits(self):
        runtime=make_runtime()
        cfg=GenerationConfig(max_new_tokens=4,repetition_penalty=1.22,
                            presence_penalty=.35,frequency_penalty=.2,penalty_window=3)
        tokens=list(runtime.encode("alpha beta beta gamma").token_ids)
        counts=RollingPenaltyWindow(tokens,cfg.penalty_window)
        for count in range(4):
            logits=runtime.infer_sequence(runtime.encode("alpha beta")).logits
            self.assertEqual(runtime._sampling_logits(logits,tokens,count,cfg),
                runtime._sampling_logits(logits,tokens,count,cfg,repetition_counts=counts.counts))
            token=tokens[count]
            tokens.append(token);counts.append(token)

    def test_cross_token_overlapping_and_earlier_longer_stop(self):
        matcher=WordStopMatcher(("beta","alpha beta gamma","gam"))
        values=[]
        for token in ("alpha","beta","gamma"):
            values.append(token);matcher.append(token)
            text=" ".join(values)
            hits=[text.find(m) for m in matcher.markers]
            self.assertEqual(matcher.first,min((v for v in hits if v>=0),default=None))
        self.assertEqual(matcher.verify("alpha beta gamma"),0)

    def test_word_stop_tail_is_bounded_and_unicode_exact(self):
        matcher=WordStopMatcher((" blå","雪 風","Ω"))
        pieces=["word"]*100+["雪","風","blå"]
        for piece in pieces:
            matcher.append(piece)
            self.assertLessEqual(len(matcher.tail),max(map(len,matcher.markers))-1)
        self.assertEqual(matcher.verify(" ".join(pieces)),(" ".join(pieces)).find("雪 風"))

    def test_real_generation_avoids_repeated_full_decode_without_a_match(self):
        runtime=make_runtime()
        cfg=GenerationConfig(max_new_tokens=12,seed=7,temperature=0.,
                             stop_strings=("impossible opaque stop sentinel",))
        with patch.object(runtime.tokenizer,"decode_ids",wraps=runtime.tokenizer.decode_ids) as decode:
            result=runtime.generate("alpha beta",cfg)
        self.assertEqual(len(result.generated_ids),12)
        self.assertEqual(decode.call_count,1)
        self.assertEqual(result.text," ".join(result.generated_tokens))

    def test_real_word_stop_before_minimum_preserves_earliest_match(self):
        runtime=make_runtime()
        cfg=GenerationConfig(max_new_tokens=4,seed=7,temperature=0.)
        baseline=runtime.generate("alpha beta",cfg)
        marker=baseline.generated_tokens[0]
        stopped=runtime.generate("alpha beta",replace(cfg,min_new_tokens=2,stop_strings=(marker,)))
        self.assertEqual(stopped.finish_reason,"stop_string")
        self.assertEqual(stopped.generated_ids,baseline.generated_ids[:2])
        self.assertEqual(stopped.text,"")


if __name__=="__main__":
    unittest.main()
