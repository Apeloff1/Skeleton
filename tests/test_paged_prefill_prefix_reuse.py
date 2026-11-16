import pytest

torch=pytest.importorskip("torch")
from skeleton.cortex.transformer import TinyTransformer
from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.model_runtime.runtime_contracts import DevicePolicy,GenerationConfig,BatchGenerationRequest
from skeleton.ai.model_runtime.paged_attention import PagedBatchSession


def runtime():
    return NativeLLMRuntime(TinyTransformer({"alpha","beta","gamma"},dim=8,ctx=48,n_heads=2,n_layers=2,seed=9),
        device_policy=DevicePolicy(requested="torch-cpu",allow_fallback=False))


def test_private_full_pages_reused_without_mutating_donor():
    rt=runtime()
    accel=rt.model._accel
    session=PagedBatchSession(accel,slots=2,context=48,max_kv_bytes=1024**2,require_gpu=False,private_prefix_scope="operator")
    try:
        donor=[1,2]*10
        a=session.logits([0],[donor])[0][0]
        first=session.states[0].pages[0]
        recipient=[1,2]*8+[3,3]
        got=session.logits([1],[recipient])[0][0]
        assert session.reused_prefix_tokens==16
        assert session.states[1].pages[0]==first and session._page_refs[first]==2
        assert got==pytest.approx(accel.logits(recipient),abs=2e-5)
        assert session.logits([0],[donor])[0][0]==a
        session.release(0)
        assert session._page_refs[first]==1 and first not in session.free
        session.release(1)
        assert session._page_refs[first]==0 and first in session.free
    finally:
        session.close()


def test_chunked_prefill_returns_short_sequence_without_waiting_for_long():
    rt=runtime()
    sess=PagedBatchSession(rt.model._accel,slots=2,context=48,max_kv_bytes=1024**2,require_gpu=False)
    try:
        windows=[[1]*30,[2]]
        ready=sess.logits_ready([0,1],windows,max_steps=4)
        assert list(ready)==[1]
        assert len(sess.states[0].tokens)==1
        ready=sess.logits_ready([0,1],[windows[0],[2,3]],max_steps=4)
        assert list(ready)==[1]
        assert len(sess.states[0].tokens)==2
        assert sess.logits_ready([0],[windows[0]],max_steps=3)=={}
        assert len(sess.states[0].tokens)==5
    finally:
        sess.close()
