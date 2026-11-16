"""Real causal-compute, tokenizer-integrity and lossless idle-KV regressions."""
from __future__ import annotations

from array import array
import math
import threading
import unittest
from unittest.mock import PropertyMock, patch

from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime, NativeConversationSession
from skeleton.ai.model_runtime.flgb_model_runtime import VocabularyManifest, digest_json
from skeleton.ai.model_runtime.runtime_contracts import GenerationConfig
from skeleton.ai.model_runtime.tokenization import NativeTokenizer, TokenizerContractError
from skeleton.ai.runtime.inference.native_runtime import NativeRuntimeLocalModel
from skeleton.ai.runtime.inference.local import LocalInferenceRequest
from skeleton.ai.runtime.inference.private_prefill import _scope
from skeleton.cortex.bpe import BytePairEncoder
from skeleton.cortex.transformer import TinyTransformer, TransformerBlock, KVCache, _poll_matvec


def runtime(*, layers=2, heads=2, ffn="swiglu", norm="rms", position="rope", width=16):
    return NativeLLMRuntime(TinyTransformer(
        vocab=("alpha","beta","gamma","delta","mesh","shader","game","render","test","code","world"),
        dim=width, ctx=64, n_layers=layers, n_heads=heads, d_ff=width,
        seed=72, norm=norm, ffn_kind=ffn, position_mode=position,
    ))


TEXT="alpha beta gamma delta mesh shader game render test code world alpha beta gamma delta mesh shader game render test"


class LastQueryTests(unittest.TestCase):
    def test_last_only_matches_complete_causal_graph_bit_for_bit(self):
        for layers in (1,2,3):
            for position in ("rope","learned_rope"):
                for norm,ffn in (("ln","gelu"),("rms","swiglu")):
                    rt=runtime(layers=layers,position=position,norm=norm,ffn=ffn)
                    ids=rt.encode(TEXT).token_ids
                    all_rows,_=rt.model._forward(ids,retain_cache=True)
                    expected=rt.model._unembed(all_rows[-1])
                    with patch.object(TransformerBlock,"forward_inference",
                                      autospec=True,side_effect=TransformerBlock.forward_inference) as calls:
                        actual=rt.model._logits(ids)
                    self.assertEqual(expected,actual)
                    self.assertEqual(calls.call_count,layers)
                    self.assertTrue(calls.call_args.kwargs["last_only"])
                    self.assertEqual([c.kwargs["last_only"] for c in calls.call_args_list],
                                     [False]*(layers-1)+[True])

    def test_real_final_layer_projection_work_reduced(self):
        rt=runtime(layers=2)
        model=rt.model
        ids=rt.encode(TEXT).token_ids
        final=model.layers[-1]
        import skeleton.cortex.transformer as module
        import skeleton.cortex.attn as attention
        original=module.matvec
        counts={}
        def count(matrix, vector):
            counts[id(matrix)]=counts.get(id(matrix),0)+1
            return original(matrix,vector)
        with patch.object(module,"matvec",side_effect=count), patch.object(attention,"matvec",side_effect=count):
            expected=model._unembed(model._forward(ids,retain_cache=False)[0][-1])
        baseline=dict(counts)
        counts.clear()
        with patch.object(module,"matvec",side_effect=count), patch.object(attention,"matvec",side_effect=count):
            actual=model._logits(ids)
        self.assertEqual(actual,expected)
        for matrix in (final.Wq,final.Wo,final.W1,final.Wu,final.W2):
            self.assertEqual(baseline[id(matrix)],len(ids))
            self.assertEqual(counts[id(matrix)],1)
        for matrix in (final.Wk,final.Wv):
            self.assertEqual(counts[id(matrix)],len(ids))

    def test_streamed_full_layer_retains_all_hidden_rows(self):
        rt=runtime()
        ids=rt.encode(TEXT).token_ids
        hidden=rt.model._encode(ids)
        for layer in rt.model.layers:
            old,_=layer.forward(hidden,rt.model.n_heads,retain_cache=True)
            streamed=layer.forward_inference(hidden,rt.model.n_heads)
            self.assertEqual(streamed,old)
            hidden=streamed

    def test_seeded_no_cache_generation_and_terminal_receipt_parity(self):
        rt=runtime()
        cfg=GenerationConfig(max_new_tokens=4,temperature=.7,top_k=4,seed=42,use_cache=False)
        with patch.object(rt.model,"_forward",wraps=rt.model._forward):
            old=rt.generate(TEXT,cfg)
        optimized=rt.generate(TEXT,cfg)
        self.assertEqual(old.generated_ids,optimized.generated_ids)
        self.assertEqual(old.text,optimized.text)
        self.assertEqual(old.replay_receipt,optimized.replay_receipt)

    def test_short_context_and_custom_forward_keep_canonical_fallback(self):
        rt=runtime()
        with patch.object(TransformerBlock,"forward_inference",side_effect=AssertionError("unexpected optimization")):
            rt.model._logits(rt.encode("alpha beta").token_ids)
            with patch.object(rt.model,"_forward",wraps=rt.model._forward):
                rt.model._logits(rt.encode(TEXT).token_ids)

    def test_projection_chunks_preserve_exact_sum_and_interrupt_between_batches(self):
        matrix=[[float(i+j)/7 for j in range(8)] for i in range(300)]
        vector=[.3,-.6,.1,.2,-.7,1.,-.4,.8]
        from skeleton.cortex.attn import matvec
        calls=[]
        self.assertEqual(_poll_matvec(matrix,vector,lambda:calls.append(1)),matvec(matrix,vector))
        self.assertEqual(len(calls),3)
        def interrupt():
            calls.append(1)
            if len(calls)==5:
                raise TimeoutError("interrupt projection")
        with self.assertRaisesRegex(TimeoutError,"interrupt projection"):
            _poll_matvec(matrix,vector,interrupt)

    def test_interrupted_cached_unembed_resets_partial_bank(self):
        rt=runtime()
        model=rt.model
        cache=KVCache(model.n_layers,rt.limits.max_context)
        ids=rt.encode("alpha beta gamma").token_ids
        rt.infer_sequence(rt.encode("alpha beta"),cache=cache)
        def interrupted(*args,**kwargs):
            raise TimeoutError("projection interruption")
        with patch.object(model,"_project_logits",side_effect=interrupted):
            with self.assertRaises(TimeoutError):
                model._logits_window(ids,cache,interrupt=lambda:None)
        self.assertEqual(cache.tokens,[])
        self.assertEqual(cache.next_position,0)
        self.assertIsNone(cache.last_logits)
        self.assertTrue(all(not rows for rows in cache.K+cache.V))


class TokenizerHotPathTests(unittest.TestCase):
    def test_canonical_manifest_digest_stable_without_repeated_serialization(self):
        rt=runtime()
        tokenizer=rt.tokenizer
        expected=digest_json({
            "schema":tokenizer.SCHEMA,
            "vocabulary_manifest_digest":tokenizer.vocabulary_manifest.digest,
            "bpe":None,"normalization":"model-native-exact-source-digest-v1",
        })
        self.assertEqual(tokenizer.digest,expected)
        with patch.object(VocabularyManifest,"digest",new_callable=PropertyMock,
                          side_effect=AssertionError("re-encoded immutable manifest")):
            tokenizer.assert_unchanged()
            tokenizer.encode_sequence(TEXT)
            tokenizer.decode_ids((1,2))
            self.assertEqual(tokenizer.checkpoint()["digest"],expected)

    def test_live_lookup_mapping_drift_is_rejected_before_encode(self):
        rt=runtime()
        token=rt.model.itos[1]
        rt.model.stoi[token]=2
        with self.assertRaisesRegex(TokenizerContractError,"lookup"):
            rt.tokenizer.encode_ids(token)

    def test_bool_lookup_alias_and_extra_keys_cannot_pass_identity(self):
        for change in ("bool","extra"):
            rt=runtime()
            if change=="bool":
                rt.model.stoi[rt.model.itos[1]]=True
            else:
                rt.model.stoi["alias"]=1
            with self.assertRaisesRegex(TokenizerContractError,"lookup"):
                rt.tokenizer.assert_unchanged()

    def test_bpe_change_and_attachment_are_still_detected(self):
        rt=runtime()
        bpe=BytePairEncoder(merges=4)
        bpe.fit(["alpha alpha beta beta "*10])
        rt.model.bpe=bpe
        with self.assertRaisesRegex(TokenizerContractError,"BPE"):
            rt.tokenizer.assert_unchanged()
        tokenizer=NativeTokenizer(rt.model)
        tokenizer.assert_unchanged()
        bpe.merges.append(("a","l","al"))
        with self.assertRaisesRegex(TokenizerContractError,"BPE"):
            tokenizer.assert_unchanged()

    def test_original_tokenizer_identity_bytes_survive_bpe_checkpoint(self):
        rt=runtime()
        bpe=BytePairEncoder(merges=4)
        bpe.fit(["alpha beta alpha beta "*10])
        rt.model.bpe=bpe
        rt.refresh_model_identity()
        restored=NativeLLMRuntime.restore(rt.checkpoint())
        self.assertEqual(restored.tokenizer.digest,rt.tokenizer.digest)
        self.assertEqual(restored.encode(TEXT),rt.encode(TEXT))


class PackedPrivateKVTests(unittest.TestCase):
    def test_actual_cpu_bank_packs_exact_values_and_reduces_retained_bytes(self):
        rt=runtime(width=64)
        cache=KVCache(rt.model.n_layers,rt.limits.max_context)
        rt.infer_sequence(rt.encode(TEXT),cache=cache)
        before=[[[float(x) for x in row] for row in layer] for layer in cache.K+cache.V]
        original=NativeConversationSession._retained_prefix_size(cache)
        self.assertTrue(NativeConversationSession._compact_retained_prefix(cache,width=rt.model.dim,budget=8*1024**2))
        actual=NativeConversationSession._retained_prefix_size(cache)
        self.assertLess(actual,original)
        self.assertTrue(all(type(row) is array and row.typecode=="d" for layer in cache.K+cache.V for row in layer))
        self.assertEqual(before,[[list(row) for row in layer] for layer in cache.K+cache.V])
        extended=rt.encode(TEXT+" alpha")
        warm=rt.infer_sequence(extended,cache=cache)
        cold=rt.infer_sequence(extended)
        self.assertEqual(warm.logits,cold.logits)

    def test_packed_rows_preserve_negative_zero_and_exact_float_bits(self):
        rt=runtime()
        cache=KVCache(rt.model.n_layers,rt.limits.max_context)
        rt.infer_sequence(rt.encode("alpha beta gamma"),cache=cache)
        cache.K[0][0][0]=-0.0
        self.assertTrue(NativeConversationSession._compact_retained_prefix(cache,width=rt.model.dim,budget=1024**2))
        self.assertEqual(math.copysign(1.0,cache.K[0][0][0]),-1.0)

    def test_compaction_denies_small_budget_nonfinite_and_wrong_geometry(self):
        for alteration in ("budget","nan","shape","origin"):
            rt=runtime()
            cache=KVCache(rt.model.n_layers,rt.limits.max_context)
            rt.infer_sequence(rt.encode("alpha beta gamma"),cache=cache)
            budget=1024**2
            if alteration=="budget": budget=1
            elif alteration=="nan": cache.K[0][0][0]=float("nan")
            elif alteration=="shape": cache.K[0][0].pop()
            else: cache.next_position+=1
            self.assertFalse(NativeConversationSession._compact_retained_prefix(cache,width=rt.model.dim,budget=budget))

    def test_private_pool_reuses_compacted_history_without_changing_output(self):
        warm=NativeRuntimeLocalModel(runtime())
        cold=NativeRuntimeLocalModel(runtime())
        owner,session="private-host","one"
        warm.register_private_prefill(owner,session)
        def run(backend,text,scoped):
            request=LocalInferenceRequest(text,max_output_tokens=3,temperature=.6,top_k=4,seed=29)
            if scoped:
                prepared=backend.prepare_input(request,scope_digest=_scope(owner,session))
                return backend.infer_prepared(request,threading.Event(),prepared)
            return backend.infer(request,threading.Event())
        run(warm,"alpha beta gamma delta",True)
        pool=warm._private_prefill
        entry=pool._entries[_scope(owner,session)]
        self.assertIsNotNone(entry.cache)
        self.assertTrue(any(type(row) is array for layer in entry.cache.K for row in layer))
        result=run(warm,"alpha beta gamma shader",True)
        expected=run(cold,"alpha beta gamma shader",False)
        self.assertEqual(result.text,expected.text)
        self.assertEqual(result.execution_receipt_digest,expected.execution_receipt_digest)
        self.assertGreater(warm.private_prefill_statistics()["reused_prefix_tokens"],0)
        warm.forget_private_prefill(owner,session)
        self.assertEqual(warm.private_prefill_statistics()["retained_scopes"],0)


if __name__=="__main__":
    unittest.main()
