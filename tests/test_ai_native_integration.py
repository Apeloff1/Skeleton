import threading
from skeleton.cortex.transformer import TinyTransformer
from skeleton.ai.model_runtime import DevicePolicy, NativeLLMRuntime
from skeleton.ai.runtime.inference.local import LocalInferenceRequest
from skeleton.ai.integrations.native_model import NativeRuntimeBackend

def test_native_runtime_reaches_local_inference_contract():
    model=TinyTransformer(vocab=("user:","hello","assistant:","world","token"),dim=8,ctx=16,seed=11,n_heads=2,n_layers=2,d_ff=16)
    runtime=NativeLLMRuntime(model,device_policy=DevicePolicy("cpu"))
    backend=NativeRuntimeBackend(runtime)
    result=backend.infer(LocalInferenceRequest(prompt="hello",max_output_tokens=2,seed=7),threading.Event())
    assert result.model_digest == runtime.model_digest
    assert backend.tokenizer_digest == runtime.tokenizer.digest
    assert result.output_tokens == 2
    assert result.response_id.startswith("native:")

def test_native_bridge_identity_is_bound():
    model=TinyTransformer(vocab=("user:","hello","assistant:","world"),dim=8,ctx=16,seed=12,n_heads=2,n_layers=2,d_ff=16)
    runtime=NativeLLMRuntime(model,device_policy=DevicePolicy("cpu"))
    backend=NativeRuntimeBackend(runtime)
    assert backend.model_digest == runtime.model_digest
    assert backend.tokenizer_digest == runtime.tokenizer.digest


def test_context_digest_changes_native_execution_identity():
    model=TinyTransformer(vocab=("user:","hello","assistant:","world","token"),dim=8,ctx=16,seed=13,n_heads=2,n_layers=2,d_ff=16)
    runtime=NativeLLMRuntime(model,device_policy=DevicePolicy("cpu"))
    backend=NativeRuntimeBackend(runtime)
    cancel=threading.Event()
    first=backend.infer(LocalInferenceRequest(prompt="hello",max_output_tokens=2,seed=7,context_digest="a"*64),cancel)
    second=backend.infer(LocalInferenceRequest(prompt="hello",max_output_tokens=2,seed=7,context_digest="b"*64),cancel)
    assert first.text == second.text
    assert first.response_id != second.response_id


def test_context_digest_is_part_of_local_request_identity():
    first=LocalInferenceRequest(prompt="hello",context_digest="a"*64)
    second=LocalInferenceRequest(prompt="hello",context_digest="b"*64)
    assert first.rendered_input == second.rendered_input
    assert first.digest != second.digest


def test_context_digest_rejects_malformed_provenance():
    try:
        LocalInferenceRequest(prompt="hello",context_digest="not-a-digest")
    except ValueError as exc:
        assert "context_digest" in str(exc)
    else:
        raise AssertionError("malformed context provenance must fail closed")
