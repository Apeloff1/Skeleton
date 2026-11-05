"""Actual model graph smoke with serving-aligned chat tokenization and receipt."""
from __future__ import annotations
from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.model_runtime.chat_engine import NativeChatEngine
from skeleton.ai.model_runtime.chat_protocol import ChatTranscript
from skeleton.ai.model_runtime.runtime_contracts import GenerationConfig
from .canonical import require_sha,digest
from .errors import reject


def native_smoke(runtime:NativeLLMRuntime,*,expected_model_sha256:str)->dict:
    require_sha(expected_model_sha256,"smoke-model")
    if type(runtime) is not NativeLLMRuntime:
        reject("smoke-real-native")
    runtime.assert_model_unchanged()
    if runtime.model_digest!=expected_model_sha256:
        reject("smoke-identity")
    transcript=ChatTranscript.parse([{
        "role":"user",
        "content":"Give the number following one.",
    }])
    result=NativeChatEngine(runtime).generate(
        transcript,GenerationConfig(max_new_tokens=2,seed=0,temperature=1.0),
    ).generation
    if len(result.generated_ids)!=2:
        reject("smoke-no-real-generation")
    runtime.assert_model_unchanged()
    return {
        "schema":"skeleton.native-supervised.graph-smoke.v1",
        "model_sha256":runtime.model_digest,
        "tokenizer_sha256":runtime.tokenizer.digest,
        "output_sha256":digest({"text":result.text}),
        "replay_sha256":result.replay_receipt.digest,
        "generated_tokens":len(result.generated_ids),
        "actual_native_graph_executed":True,
        "answer_correctness_proven":False,
        "production_authorized":False,
    }
