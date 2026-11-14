"""Pre-admit max prompt/generation context for every challenge before execution."""
from __future__ import annotations
from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.model_runtime.chat_protocol import ChatTranscript
from skeleton.ai.model_runtime.chat_engine import NativeChatEngine
from .challenge_catalog import iter_challenges
from .canonical import require_int,digest
from .errors import reject


def check(runtime:NativeLLMRuntime,*,max_new_tokens:int=32)->dict:
    if type(runtime) is not NativeLLMRuntime:
        reject("context-runtime")
    require_int(max_new_tokens,"context-reserved",1,256)
    if max_new_tokens>=runtime.limits.max_context:
        reject("context-reservation-overrun")
    engine=NativeChatEngine(runtime)
    failures=[]
    sizes=[]
    for case in iter_challenges():
        transcript=ChatTranscript.parse([{
            "role":"user","content":case.prompt,
        }])
        actual=engine.prompt_token_count(transcript)
        sizes.append(actual)
        if actual+max_new_tokens>runtime.limits.max_context:
            failures.append(case.case_id)
    return {
        "schema":"skeleton.native-supervised.eval-context-preflight.v1",
        "cases":len(sizes),
        "maximum_prompt_tokens":max(sizes) if sizes else 0,
        "maximum_generation_tokens":max_new_tokens,
        "model_context_tokens":runtime.limits.max_context,
        "unfittable_cases":failures,
        "all_contexts_fit":len(sizes)==768 and not failures,
        "source_sha256":digest({"prompt_token_counts":sizes}),
        "generation_executed":False,
        "case_exemptions":0,
    }
