"""Calibration and latency statistics that never assert release readiness."""
from __future__ import annotations
from dataclasses import dataclass
import math
from statistics import mean,median
from ..authority.canonical import ContractViolation


@dataclass(frozen=True,slots=True)
class Sample:
    latency_ms:float
    prompt_tokens:int
    completion_tokens:int
    accepted:bool

    def __post_init__(self):
        if type(self.latency_ms) not in (int,float) or not math.isfinite(self.latency_ms) or self.latency_ms<0:
            raise ContractViolation("invalid model latency measurement")
        if (type(self.prompt_tokens) is not int or type(self.completion_tokens) is not int
                or min(self.prompt_tokens,self.completion_tokens)<0):
            raise ContractViolation("invalid model token count")
        if type(self.accepted) is not bool:
            raise ContractViolation("invalid acceptance evidence")


def summarize(samples:list[Sample])->dict:
    if not samples or len(samples)>1_000_000 or any(not isinstance(s,Sample) for s in samples):
        raise ContractViolation("bounded numeric samples required")
    latencies=sorted(s.latency_ms for s in samples)
    percentile_index=math.ceil(.95*len(latencies))-1
    return {"observations":len(samples),"pass_count":sum(s.accepted for s in samples),
            "pass_ratio":mean(int(s.accepted) for s in samples),
            "median_latency_ms":median(latencies),"p95_latency_ms":latencies[percentile_index],
            "total_prompt_tokens":sum(s.prompt_tokens for s in samples),
            "total_generated_tokens":sum(s.completion_tokens for s in samples),
            "release_certified":False}
