"""Read-only exact native challenge prompt/answer vocabulary gap measurement."""
from __future__ import annotations
from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.model_runtime.chat_protocol import ChatTranscript
from .challenge_catalog import iter_challenges
from .errors import reject


def inspect(runtime:NativeLLMRuntime)->dict:
    if type(runtime) is not NativeLLMRuntime:
        reject("lexical-gap-runtime")
    runtime.assert_model_unchanged()
    total_prompt=unknown_prompt=total_answer=unknown_answer=0
    domains={}
    for case in iter_challenges():
        prompt_ids=runtime.model._ids(
            ChatTranscript.parse([{"role":"user","content":case.prompt}]).format_prompt()
        )
        answer_ids=runtime.model._ids(case.expected)
        if not prompt_ids or not answer_ids:
            reject("lexical-gap-empty-ids")
        p_unknown=sum(t==runtime.model.unk for t in prompt_ids)
        a_unknown=sum(t==runtime.model.unk for t in answer_ids)
        total_prompt+=len(prompt_ids)
        total_answer+=len(answer_ids)
        unknown_prompt+=p_unknown
        unknown_answer+=a_unknown
        item=domains.setdefault(case.domain,{"prompt_unknown":0,"answer_unknown":0,
                                              "cases":0})
        item["cases"]+=1
        item["prompt_unknown"]+=p_unknown
        item["answer_unknown"]+=a_unknown
    return {
        "schema":"skeleton.native-supervised.lexical-gaps.v1",
        "model_sha256":runtime.model_digest,
        "prompt_tokens":total_prompt,
        "answer_tokens":total_answer,
        "unknown_prompt_tokens":unknown_prompt,
        "unknown_answer_tokens":unknown_answer,
        "prompt_coverage_ppm":(total_prompt-unknown_prompt)*1000000//total_prompt,
        "answer_coverage_ppm":(total_answer-unknown_answer)*1000000//total_answer,
        "domains":domains,
        "vocabulary_mutated":False,
        "evaluation_fit_performed":False,
        "release_certified":False,
    }
