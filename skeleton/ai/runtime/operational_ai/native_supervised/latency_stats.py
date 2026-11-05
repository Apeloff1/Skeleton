"""Observed inference latency and token statistics, no synthetic timing."""
from __future__ import annotations
from .challenge_runner import ChallengeRun
from .canonical import require_int
from .errors import reject


def nearest_rank(values:list[int],percentile:int)->int:
    require_int(percentile,"percentile",1,100)
    if type(values) is not list or not values:
        reject("latency-empty")
    if any(type(v) is not int or v<0 for v in values):
        reject("latency-bad-sample")
    values=sorted(values)
    index=(len(values)*percentile+99)//100-1
    return values[index]


def summarize(run:ChallengeRun)->dict:
    if type(run) is not ChallengeRun or not run.results:
        reject("latency-run")
    durations=[x.latency_ms for x in run.results]
    generated=[x.generated_tokens for x in run.results]
    return {
        "schema":"skeleton.native-supervised.inference-timing.v1",
        "cases":len(durations),
        "p50_ms":nearest_rank(durations,50),
        "p95_ms":nearest_rank(durations,95),
        "p99_ms":nearest_rank(durations,99),
        "total_tokens":sum(generated),
        "total_elapsed_ms":sum(durations),
        "measured_native_requests":True,
        "device_qualified":False,
        "hardware_repeatability_verified":False,
    }
