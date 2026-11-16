import pytest

torch=pytest.importorskip("torch")
from skeleton.cortex.transformer import TinyTransformer
from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.model_runtime.runtime_contracts import DevicePolicy,RuntimeContractError
from skeleton.ai.model_runtime.kernel_qualification import measure,MeasuredKernelProfile


def test_cpu_measurement_executes_but_cannot_authorize_gpu():
    rt=NativeLLMRuntime(TinyTransformer({"a","b","c"},dim=8,ctx=8,n_heads=2,seed=1),
        device_policy=DevicePolicy(requested="torch-cpu",allow_fallback=False))
    proof=measure(rt,["a b","b c"],repeats=3,max_new_tokens=1,
        max_workspace_bytes=1024**2,paged_kv_bytes=1024**2,require_gpu=False)
    assert len(proof["rows"])==6
    assert all(row["exact"] for row in proof["rows"])
    assert proof["physical_gpu"] is False
    with pytest.raises(RuntimeContractError,match="CUDA"):
        MeasuredKernelProfile.admit(rt,proof,proof["measurement_sha256"])
