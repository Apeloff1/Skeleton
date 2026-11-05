"""Non-interpolated percentile and throughput metrics for finite runtime trials."""
from __future__ import annotations
import math
from .contracts import QualificationHeld


def summarize(times_ns:list[int], generated_tokens:list[int]) -> dict:
    if (type(times_ns) is not list or type(generated_tokens) is not list
        or not times_ns or len(times_ns)!=len(generated_tokens) or len(times_ns)>256):
        raise QualificationHeld('invalid bounded native trial measurements')
    if (any(type(x)is not int or x<=0 for x in times_ns) or
        any(type(y)is not int or y<0 for y in generated_tokens)):
        raise QualificationHeld('invalid monotonic latency or token metrics')
    ordered=sorted(times_ns)
    def percentile(numerator:int,denominator:int)->int:
        position=max(0,(numerator*len(ordered)+denominator-1)//denominator-1)
        return ordered[position]
    total_ns=sum(times_ns)
    tokens=sum(generated_tokens)
    rate=round(tokens*1e9/total_ns,3)
    if not math.isfinite(rate):raise QualificationHeld('invalid observed token rate')
    return {'observations':len(ordered),'p50_ns':percentile(50,100),
        'p95_ns':percentile(95,100),'p99_ns':percentile(99,100),
        'max_ns':ordered[-1], 'total_ns':total_ns,'generated_tokens':tokens,
        'generated_tokens_per_second':rate,
        'kind':'observed-native-returns-not-sampling-prefill-qualified'}
