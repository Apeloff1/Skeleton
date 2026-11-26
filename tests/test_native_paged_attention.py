import pytest

torch = pytest.importorskip("torch")
from skeleton.cortex.transformer import TinyTransformer
from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.model_runtime.runtime_contracts import BatchGenerationRequest, DevicePolicy, GenerationConfig
from skeleton.ai.model_runtime.paged_attention import PagedBatchSession


def runtime(device):
    model = TinyTransformer({"a","b","c"}, dim=8, ctx=32, n_heads=2, n_layers=2, d_ff=16, seed=4)
    return NativeLLMRuntime(model, device_policy=DevicePolicy(requested=device, allow_fallback=False))


@pytest.mark.parametrize("device", ["torch-cpu", pytest.param("cuda", marks=pytest.mark.skipif(not torch.cuda.is_available(), reason="CUDA unavailable"))])
def test_paged_actual_kv_suffix_and_page_reuse(device):
    rt=runtime(device)
    a=rt.model._accel
    with a._state_lock:
        session=PagedBatchSession(a, slots=3, context=32, max_kv_bytes=1024**2, require_gpu=device=="cuda")
        try:
            windows=[[1,2,3]*6,[3,2],[1]]
            first=session.logits([0,1,2],windows)
            for row,window in zip(first,windows):
                assert row[0] == pytest.approx(a.logits(window),abs=2e-5)
            old=list(session.states[0].pages)
            new=windows[0]+[1]
            actual=session.logits([0,1],[new,[3,2,1]])
            assert actual[0][0] == pytest.approx(a.logits(new),abs=2e-5)
            assert session.states[0].pages==old
            ids=set(session.states[2].pages)
            session.release(2)
            assert ids.issubset(session.free)
            shifted=new[1:]+[2]
            row=session.logits([0],[shifted])[0]
            assert row[3]==1
            assert row[0]==pytest.approx(a.logits(shifted),abs=2e-5)
        finally:
            session.close()


def test_paged_generation_canonical_receipt_and_budget():
    rt=runtime("torch-cpu")
    config=GenerationConfig(max_new_tokens=3,temperature=0,use_cache=True)
    requests=[BatchGenerationRequest("a","a b",config),BatchGenerationRequest("b","c",config)]
    serial=rt.generate_batch(requests)
    rt.model._accel.reset_decode_cache()
    batched=rt.generate_fused_batch(requests,max_workspace_bytes=1024**2,paged_kv_bytes=1024**2,require_gpu=False)
    assert [r.result.generated_ids for r in batched]==[r.result.generated_ids for r in serial]
    assert all(r.result.usage.kv_peak_bytes>0 for r in batched)
    with pytest.raises(MemoryError):
        rt.generate_fused_batch(requests,max_workspace_bytes=1024**2,paged_kv_bytes=1,require_gpu=False)
