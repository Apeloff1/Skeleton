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
