"""Detect output formats unreachable by the current native tokenization grammar.

This is critical: the word-level cortex tokenizer strips punctuation and
case. It cannot emit literal CSV commas, JSON braces or uppercase source
labels without an independently qualified output adapter. Unrepresentable
answers remain FAILURES, never erased from the benchmark denominator.
"""
from __future__ import annotations
from dataclasses import dataclass
from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from .challenge_schema import Challenge
from .challenge_catalog import iter_challenges
from .canonical import digest
from .errors import reject


@dataclass(frozen=True,slots=True)
class Representation:
    case_id:str
    expected_sha256:str
    lexical_ids:int
    unknown_ids:int
    exact_native_renderable:bool

    def record(self)->dict:
        return {k:getattr(self,k) for k in self.__dataclass_fields__}


def inspect(runtime:NativeLLMRuntime,case:Challenge)->Representation:
    if type(runtime) is not NativeLLMRuntime or type(case) is not Challenge:
        reject("representation-types")
    runtime.assert_model_unchanged()
    ids=runtime.model._ids(case.expected)
    if not ids:
        return Representation(case.case_id,case.expected_sha256,0,0,False)
    decoded=runtime.tokenizer.decode_ids(ids)
    return Representation(
        case.case_id,case.expected_sha256,len(ids),
        sum(x==runtime.model.unk for x in ids),
        decoded.strip()==case.expected.strip(),
    )


def full_audit(runtime:NativeLLMRuntime)->dict:
    if type(runtime) is not NativeLLMRuntime:
        reject("representation-runtime")
    cases=tuple(iter_challenges())
    if len(cases)!=768:
        reject("representation-cases")
    proof=tuple(inspect(runtime,c) for c in cases)
    domains={}
    for challenge,result in zip(cases,proof):
        row=domains.setdefault(challenge.domain,{"renderable":0,"unrenderable":0})
        row["renderable" if result.exact_native_renderable else "unrenderable"]+=1
    return {
        "schema":"skeleton.native-supervised.representability.v1",
        "native_model_sha256":runtime.model_digest,
        "native_tokenizer_sha256":runtime.tokenizer.digest,
        "cases":len(proof),
        "exact_renderable":sum(x.exact_native_renderable for x in proof),
        "unrenderable":sum(not x.exact_native_renderable for x in proof),
        "by_domain":domains,
        "source_sha256":digest([x.record() for x in proof]),
        "unrenderable_counted_as_pass":False,
        "native_model_qualified":False,
        "output_adapter_qualified":False,
    }
