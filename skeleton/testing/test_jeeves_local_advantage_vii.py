"""Actual local prefill, sparse retrieval and context-budget regressions."""
from __future__ import annotations

import asyncio
import threading
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.runtime.inference.native_runtime import NativeRuntimeLocalModel
from skeleton.ai.runtime.inference.private_prefill import PrivatePrefillPool,_scope
from skeleton.ai.runtime.inference.local import LocalInferenceRequest,LocalInferenceCancelled
from skeleton.ai.model_runtime.offline_chat import OfflineChatStore
from skeleton.ai.model_runtime.runtime_contracts import RuntimeContractError
from skeleton.app.offline_knowledge import OfflineKnowledgeLibrary,LocalKnowledgeHit
from skeleton.app.offline_grounding import prepare_evidence,preserves_excerpt_anchors,validate_evidence
from skeleton.app.local_ai import OfflineAISession,OfflineContextBudgetError
from skeleton.app.offline_http import OfflineHTTPApplication
from skeleton.cortex.transformer import TinyTransformer


def native(context=512):
    return NativeRuntimeLocalModel(NativeLLMRuntime(TinyTransformer(
        vocab=("user","assistant","hello","world","alpha","beta","gamma","delta",
               "renderer","shader","source","local","texture","coverage","answer","evidence"),
        dim=8,ctx=context,n_heads=2,n_layers=2,d_ff=8,seed=41,
    )))


class NativePrefillTests(unittest.TestCase):
    def run_request(self,backend,request,owner="private-owner",session="session-one"):
        backend.register_private_prefill(owner,session)
        prepared=backend.prepare_input(request,scope_digest=_scope(owner,session))
        return backend.infer_prepared(request,threading.Event(),prepared)

    def test_scoped_lcp_reuses_real_kv_and_keeps_seeded_output(self):
        warm,cold=native(),native()
        a=LocalInferenceRequest("hello alpha beta gamma",max_output_tokens=3,seed=19,
                               temperature=.7,top_k=4)
        b=LocalInferenceRequest("hello alpha beta delta",max_output_tokens=3,seed=19,
                               temperature=.7,top_k=4)
        self.run_request(warm,a)
        self.assertEqual(warm.private_prefill_statistics()["retained_scopes"],1)
        result=self.run_request(warm,b)
        reference=cold.infer(b,threading.Event())
        self.assertEqual(result.text,reference.text)
        self.assertEqual(result.response_id,reference.response_id)
        self.assertEqual(result.execution_receipt_digest,reference.execution_receipt_digest)
        self.assertGreater(warm.private_prefill_statistics()["reused_prefix_tokens"],0)

    def test_unregistered_and_other_owner_never_reuse(self):
        backend=native()
        request=LocalInferenceRequest("hello alpha beta",max_output_tokens=2)
        self.run_request(backend,request)
        before=backend.private_prefill_statistics()["reused_prefix_tokens"]
        backend.infer(request,threading.Event())
        self.run_request(backend,request,owner="different-owner")
        self.run_request(backend,request,session="different-session")
        self.assertEqual(backend.private_prefill_statistics()["reused_prefix_tokens"],before)

    def test_forget_is_scope_specific_and_fences_old_publication(self):
        backend=native()
        request=LocalInferenceRequest("hello alpha beta",max_output_tokens=2)
        self.run_request(backend,request)
        self.run_request(backend,request,session="other")
        pool=backend._private_prefill
        key=_scope("private-owner","session-one")
        prepared=backend.prepare_input(request,scope_digest=key)
        lease=pool.checkout(key,backend.execution_profile_digest,prepared.token_sequence.token_ids)
        self.assertIsNotNone(lease)
        pool.forget("private-owner","session-one")
        pool.register("private-owner","session-one")
        self.assertFalse(pool.publish(lease,prepared.token_sequence.token_ids,backend.execution_profile_digest))
        self.assertEqual(pool.stats()["retained_scopes"],1)
        pool.forget("private-owner")
        self.assertEqual(pool.stats()["retained_scopes"],0)

    def test_ttl_expires_bound_cache(self):
        backend=native()
        with patch("skeleton.ai.runtime.inference.private_prefill.time.monotonic",return_value=100.):
            self.run_request(backend,LocalInferenceRequest("hello alpha",max_output_tokens=2))
            self.assertEqual(backend.private_prefill_statistics()["retained_scopes"],1)
        with patch("skeleton.ai.runtime.inference.private_prefill.time.monotonic",return_value=221.):
            self.assertEqual(backend.private_prefill_statistics()["retained_scopes"],0)

    def test_runtime_failure_cannot_republish_detached_prefix(self):
        backend=native()
        request=LocalInferenceRequest("hello alpha beta",max_output_tokens=2)
        self.run_request(backend,request)
        with patch.object(backend.runtime,"stream_sequence",side_effect=LocalInferenceCancelled("cancelled")):
            with self.assertRaises(LocalInferenceCancelled):
                self.run_request(backend,request)
        self.assertEqual(backend.private_prefill_statistics()["retained_scopes"],0)

    def test_small_pool_and_scope_limit_are_enforced(self):
        backend=native()
        backend._private_prefill=PrivatePrefillPool(backend.runtime,max_bytes=1,max_scopes=2)
        request=LocalInferenceRequest("hello alpha",max_output_tokens=2)
        for i in range(4):
            self.run_request(backend,request,session=str(i))
        stats=backend.private_prefill_statistics()
        self.assertEqual(stats["registered_scopes"],2)
        self.assertEqual(stats["retained_estimated_python_bytes"],0)

    def test_actual_ephemeral_session_uses_and_revokes_prefill(self):
        backend=native()
        session=OfflineAISession(backend)
        asyncio.run(session.ask("hello alpha",max_output_tokens=2))
        asyncio.run(session.ask("world beta",max_output_tokens=2))
        self.assertGreater(backend.private_prefill_statistics()["reused_prefix_tokens"],0)
        session.clear()
        self.assertEqual(backend.private_prefill_statistics()["retained_scopes"],0)

    def test_http_persistent_turns_reuse_and_delete_revokes(self):
        backend=native()
        with TemporaryDirectory() as folder:
            app=OfflineHTTPApplication(backend,Path(folder)/"chat.sqlite",token="t"*64)
            try:
                _,created=app.dispatch("POST","/v1/sessions",{})
                sid=created["session_id"]
                for i,prompt in enumerate(("hello alpha","world beta")):
                    status,result=app.dispatch("POST",f"/v1/sessions/{sid}/turn",{
                        "message":prompt,"request_id":"req-"+str(i),"max_output_tokens":2})
                    self.assertEqual(status,200)
                    self.assertEqual(result["revision"],i+1)
                self.assertGreater(backend.private_prefill_statistics()["reused_prefix_tokens"],0)
                app.dispatch("DELETE",f"/v1/sessions/{sid}")
                self.assertEqual(backend.private_prefill_statistics()["retained_scopes"],0)
            finally:
                app.close()


def hit(text,doc="source-123"):
    return LocalKnowledgeHit(doc,"source","a"*64,0,0,len(text),text,10.).to_dict()


class EvidenceBudgetTests(unittest.TestCase):
    def test_variable_excerpt_keeps_exact_unicode_source_coordinates(self):
        question="shader texture"
        content="background "*30+"shader texture coverage. "+"other "*40
        broad=prepare_evidence(question,"b"*64,[hit(content)],"a"*64,"c"*64)
        narrow=prepare_evidence(question,"b"*64,[hit(content)],"a"*64,"c"*64,excerpt_chars=80)
        for manifest in (broad,narrow):
            row=manifest["citations"][0]
            self.assertEqual(row["passage"],content[row["char_start"]:row["char_end"]])
            self.assertEqual(row["passage_sha256"],sha256(row["passage"].encode()).hexdigest())
            validate_evidence(manifest,question,"b"*64,"a"*64,"c"*64)

    def test_compaction_cannot_drop_negation_or_number(self):
        q="shader"
        text="shader is suitable for a reference. "+"padding "*10+" It must not exceed 15 units."
        broad=prepare_evidence(q,"b"*64,[hit(text)],"a"*64,"c"*64)
        compact=prepare_evidence(q,"b"*64,[hit(text)],"a"*64,"c"*64,excerpt_chars=48)
        self.assertFalse(preserves_excerpt_anchors(q,broad,compact))

    def test_actual_native_budget_keeps_both_sources_or_refuses(self):
        session=OfflineAISession(native(160))
        question="shader coverage"
        texts=("shader coverage "+"local "*60,"shader coverage "+"texture "*60)
        hits=[hit(text,"source-"+str(i+123)) for i,text in enumerate(texts)]
        broad=prepare_evidence(question,"b"*64,hits,session.model_digest,session.tokenizer_digest)
        # Force bounded context fitting via actual tokenizer length, not
        # fake scores. A valid compact alternative preserves both sources.
        count=len(session.backend.runtime.tokenizer.encode_ids(
            LocalInferenceRequest(question+"\n\n"+broad["context"]).rendered_input))
        budget=160-count+10
        if not 1<=budget<=160:
            self.fail("fixture does not exercise context fit")
        selected=session.prepare_grounded_evidence(question,"b"*64,hits,budget)
        self.assertEqual(len(selected["citations"]),2)
        self.assertTrue(preserves_excerpt_anchors(question,broad,selected))
        report=session.preview_context(question,budget,grounding_context=selected["context"])
        self.assertLessEqual(report["estimated_total_tokens"],160)

    def test_preview_uses_same_rendered_text_as_actual_admission(self):
        session=OfflineAISession(native())
        manifest=prepare_evidence("shader","b"*64,[hit("shader reference is local.")],
                                  session.model_digest,session.tokenizer_digest)
        report=session.preview_context("shader",4,grounding_context=manifest["context"])
        request,_=session._request("shader\n\n"+manifest["context"],4)
        self.assertEqual(report["estimated_input_tokens"],
                         len(session.backend.runtime.tokenizer.encode_ids(request.rendered_input)))

    def test_gguf_linear_suffix_matches_original_byte_estimate(self):
        # No GGUF process is launched; test the exact historical estimator
        # over varied whole-turn costs, Unicode and odd ephemeral history.
        session=OfflineAISession.__new__(OfflineAISession)
        session.backend=SimpleNamespace(config=SimpleNamespace(context_size=130))
        session.instructions="system instructions"
        for size in (4,5,10,31):
            session.history=tuple(("user" if i%2==0 else "assistant","blå "+("x"*(i%9+8)))
                                  for i in range(size))
            history=session.history
            while True:
                req=LocalInferenceRequest("hello",instructions=session.instructions,
                                           history=history,max_output_tokens=8)
                if len(req.rendered_input.encode("utf-8"))+16<=122:
                    break
                history=history[2:]
            actual,retained=session._request("hello",8)
            self.assertEqual(retained,history)
            self.assertEqual(actual.digest,req.digest)


class SparseSearchTests(unittest.TestCase):
    def test_sparse_and_dense_routes_have_identical_verified_rank(self):
        with TemporaryDirectory() as folder:
            store=OfflineChatStore(Path(folder)/"refs.sqlite")
            try:
                library=OfflineKnowledgeLibrary(store,"a"*64,"b"*64)
                with patch("skeleton.app.offline_knowledge._require_local_headroom"):
                    library.add_text("source","alpha renderer shader "*100)
                    library.add_text("source two","alpha shader texture "*50)
                    library.add_text("unrelated","beta delta "+("world "*100))
                    for query in ("alpha shader","texture","absent"):
                        sparse=library.search(query,limit=4,diversify=True)
                        with patch("skeleton.app.offline_knowledge._SPARSE_MATCH_COUNT",0):
                            dense=library.search(query,limit=4,diversify=True)
                        self.assertEqual(sparse,dense)
                store._db.execute("UPDATE offline_documents SET content_text='mutated' WHERE title='unrelated'")
                with patch("skeleton.app.offline_knowledge._require_local_headroom"):
                    with self.assertRaises(RuntimeContractError):
                        library.search("alpha")
            finally:
                store.close()

if __name__=="__main__":
    unittest.main()
