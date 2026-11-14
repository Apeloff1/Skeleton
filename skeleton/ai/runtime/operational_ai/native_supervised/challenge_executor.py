"""Real native framed inference against source-bound never-trained challenge cases."""
from __future__ import annotations
from dataclasses import dataclass
from time import monotonic_ns
from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.model_runtime.chat_engine import NativeChatEngine
from skeleton.ai.model_runtime.chat_protocol import ChatTranscript
from skeleton.ai.model_runtime.runtime_contracts import GenerationConfig
from .challenge_schema import Challenge
from .canonical import digest,bytes_sha,require_int
from .errors import reject


@dataclass(frozen=True,slots=True)
class ProbeResult:
    case_id:str
    domain:str
    severity:str
    case_sha256:str
    prompt_sha256:str
    expected_sha256:str
    actual_sha256:str
    model_sha256:str
    tokenizer_sha256:str
    replay_receipt_sha256:str
    passed:bool
    latency_ms:int
    prompt_tokens:int
    generated_tokens:int
    finish_reason:str

    def record(self)->dict:
        return {
            **{k:getattr(self,k) for k in self.__dataclass_fields__},
            "actual_native_inference":True,
            "model_output_disclosed":False,
        }


def execute(
    runtime:NativeLLMRuntime,case:Challenge,*,max_new_tokens:int=32,
    seed:int=0,
)->ProbeResult:
    if type(runtime) is not NativeLLMRuntime or type(case) is not Challenge:
        reject("probe-native-and-case")
    require_int(max_new_tokens,"probe-token-budget",1,256)
    require_int(seed,"probe-seed",0,2**31-1)
    runtime.assert_model_unchanged()
    before=runtime.model_digest
    engine=NativeChatEngine(runtime)
    transcript=ChatTranscript.parse([{"role":"user","content":case.prompt}])
    config=GenerationConfig(
        max_new_tokens=max_new_tokens,seed=seed,temperature=1.0,
        top_k=0,top_p=1.0,use_cache=True,
    )
    started=monotonic_ns()
    generated=engine.generate(transcript,config).generation
    elapsed=(monotonic_ns()-started)//1000000
    runtime.assert_model_unchanged()
    if runtime.model_digest!=before or generated.replay_receipt.model_digest!=before:
        reject("probe-model-drift")
    if generated.replay_receipt.tokenizer_digest!=runtime.tokenizer.digest:
        reject("probe-tokenizer-drift")
    result=generated.text.strip()
    return ProbeResult(
        case.case_id,case.domain,case.severity,
        case.sha256,case.prompt_sha256,case.expected_sha256,
        bytes_sha(result.encode("utf-8")),before,runtime.tokenizer.digest,
        generated.replay_receipt.digest,
        result==case.expected.strip(),
        elapsed,generated.usage.prompt_tokens,generated.usage.generated_tokens,
        generated.finish_reason,
    )
