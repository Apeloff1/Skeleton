"""Stable model-output usage and receipt boundaries before durable job commit."""
from __future__ import annotations
from dataclasses import dataclass
from .canonical import require_int
from .errors import deny
from .result import JobResult
from .spec import WorkLimits, JobSpec


@dataclass(frozen=True, slots=True)
class ResultAssessment:
    accepted: bool
    generated_tokens: int
    max_output_tokens: int
    output_bytes: int


def assess(result:JobResult,spec:JobSpec,limits:WorkLimits)->ResultAssessment:
    if type(result) is not JobResult or type(spec) is not JobSpec or type(limits) is not WorkLimits:
        deny("result-assessment-contract")
    if (result.original_request_id!=spec.request_id or
        result.model_sha256!=spec.owner.model_sha256 or
        result.tokenizer_sha256!=spec.owner.tokenizer_sha256):
        deny("result-identity")
    if result.generated_tokens>limits.output_tokens:
        deny("result-token-overrun")
    output_bytes=len(result.text.encode("utf-8"))
    if output_bytes>262144:
        deny("result-byte-overrun")
    return ResultAssessment(True,result.generated_tokens,limits.output_tokens,output_bytes)
