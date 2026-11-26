"""Finite posterior revisit model over observed versions, not fetch volume.

A changed interval indicates at least one transition; its actual change time
and number of hidden transitions are unknown. An unchanged interval is a
no-observed-change signal, not proof that no transient change happened.
No remote timestamps, instructions or validators are treated as observations.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

_MIN_INTERVAL = 3600.
_MAX_INTERVAL = 604800.
# Fixed logarithmic rates per day; finite inference with a conservative
# log-normal prior. All rates, likelihoods and outputs are heuristic.
_RATES = tuple(2.0 ** (i / 2) for i in range(-18, 13))
_PRIOR_CENTER = math.log(1 / 7)
_PRIOR_SIGMA = 1.65
_MAX_POINTS = 512
_MIN_EXPOSURE = 60.


@dataclass(frozen=True)
class ChangeSample:
    at: float
    digest: str


def infer_revisit(samples: list[ChangeSample], *, now: float,
                  publisher_due: float | None, allowed: bool,
                  priority_value: float = .5, estimated_bytes: int = 65536) -> dict:
    if (not isinstance(samples, list) or not 1 <= len(samples) <= _MAX_POINTS
            or type(now) not in (float, int) or not math.isfinite(now)
            or type(allowed) is not bool or type(priority_value) not in (float,int)
            or not math.isfinite(priority_value) or not 0 <= priority_value <= 1
            or type(estimated_bytes) is not int or not 1 <= estimated_bytes <= 24000 * 4):
        raise ValueError("invalid revisit model envelope")
    by_time = {}
    for sample in samples:
        if (not isinstance(sample,ChangeSample) or type(sample.at) not in (float,int)
                or not math.isfinite(sample.at) or not 0 <= sample.at <= now+300
                or not isinstance(sample.digest,str) or len(sample.digest)!=64
                or any(ch not in "0123456789abcdef" for ch in sample.digest)):
            raise ValueError("invalid revisit evidence")
        by_time.setdefault(sample.at,set()).add(sample.digest)
    times=sorted(by_time)
    intervals=[]
    ambiguous=0
    for a,b in zip(times,times[1:]):
        if len(by_time[a])!=1 or len(by_time[b])!=1:
            ambiguous+=1
            continue
        elapsed=b-a
        if elapsed < _MIN_EXPOSURE:
            # bursts of observations cannot farm confidence
            continue
        intervals.append((min(90.,elapsed/86400),by_time[a]!=by_time[b]))
    # Unequal exposure intervals contribute their own likelihood; very
    # closely spaced observations cannot dominate confidence.
    weights=[]
    for rate in _RATES:
        logw=-.5*((math.log(rate)-_PRIOR_CENTER)/_PRIOR_SIGMA)**2
        for days,changed in intervals:
            x=rate*days
            logw+=math.log(max(1e-300,-math.expm1(-x))) if changed else -x
        weights.append(logw)
    peak=max(weights)
    raw=[math.exp(w-peak) for w in weights]
    normal=sum(raw)
    posterior=[w/normal for w in raw]
    def chance(seconds):
        return sum(w*(-math.expm1(-rate*seconds/86400))
                   for rate,w in zip(_RATES,posterior))
    # Invert the mixture, rather than substituting a point estimate into an
    # exponential. A higher-value resource targets a smaller stale risk.
    target=.45-.25*priority_value
    low,high=_MIN_INTERVAL,_MAX_INTERVAL
    for _ in range(32):
        mid=(low+high)/2
        if chance(mid)<target:
            low=mid
        else:
            high=mid
    interval=round(high,3)
    latest=times[-1]
    due=latest+interval
    if publisher_due is not None:
        if (type(publisher_due) not in (float,int) or not math.isfinite(publisher_due)
                or not latest <= publisher_due <= latest+604801):
            raise ValueError("invalid publisher hint")
        due=max(due,publisher_due)
    age=max(0.,now-latest)
    probability=chance(age)
    # The cost factor is a retained-text size proxy, not wire-byte telemetry.
    cost=1+.35*math.log1p(estimated_bytes/4096)
    utility=probability*(.35+.65*priority_value)/cost
    conflict=len(by_time[latest])!=1
    return {"due_at":round(due,3),"change_probability_estimate":round(probability,6),
            "observed_changes":sum(changed for _,changed in intervals),
            "interval_seconds":round(due-latest,3),
            "ready_for_review":bool(allowed and not conflict and now>=due),
            "model":"interval_censored_grid_v1",
            "qualified_intervals":len(intervals),"ambiguous_intervals":ambiguous,
            "expected_changes_per_day":round(sum(r*w for r,w in zip(_RATES,posterior)),6),
            "utility_per_cost":round(utility,6),"target_stale_risk":round(target,6),
            "fresh_consent_required":True,"network_executed":False}
