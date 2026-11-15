"""Offline comparison of revisit policies on hidden deterministic event traces.

The interval-censored estimator is exercised as shipped. The multiplicative
control is a small baseline inspired by adaptive fetch schedules, not an
execution or reproduction of Apache Nutch. No external network or real
publication cadence is sampled. Both schedulers receive identical observations
and finite request budgets; the simulator alone sees the unseen truth.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path

from skeleton.ai.webcrawler.dragon_revisit_model import ChangeSample, infer_revisit

DAY=86400
HORIZON=60*DAY
BUDGET=24
QUANTUM=3600


@dataclass(frozen=True)
class Trace:
    name: str
    changes: tuple[int,...]


def traces():
    return (
        Trace("unchanging",()),
        Trace("weekly",tuple(k*7*DAY for k in range(1,9))),
        Trace("daily_bursts",tuple(k*DAY for k in range(5,12))+tuple(k*DAY for k in range(28,36))),
        Trace("late_acceleration",tuple(k*DAY for k in (18,32,40,43,46,48,50,53,55,57,59))),
        Trace("early_then_stable",tuple(k*DAY for k in range(1,10))),
        Trace("irregular",tuple(k*DAY for k in (2,3,11,17,18,19,29,31,47,51,58))),
    )


def truth(trace, at):
    ordinal=bisect_right(trace.changes,at)
    return hashlib.sha256(str(ordinal).encode()).hexdigest()


def simulate(trace, mode):
    t=0
    samples=[]
    next_due=0
    interval=DAY
    requests=0
    changes_seen=0
    fresh_hours=0
    total_hours=0
    previous=None
    samples_lost_budget=False
    while t<HORIZON:
        if t>=next_due and requests<BUDGET:
            result=truth(trace,t)
            changed=previous is not None and previous!=result
            changes_seen+=int(changed)
            requests+=1
            samples.append(ChangeSample(float(t),result))
            if mode=="posterior":
                projected=infer_revisit(samples,now=float(t),publisher_due=None,
                                        allowed=True,priority_value=.5)
                next_due=projected["due_at"]
            elif mode=="multiplicative":
                if previous is not None:
                    interval=max(3600,min(7*DAY,interval*(.8 if changed else 1.2)))
                next_due=t+interval
            elif mode=="fixed_budget":
                next_due=t+HORIZON/BUDGET
            else:
                raise ValueError("unknown revisit baseline")
            previous=result
        if t>=next_due and requests>=BUDGET:
            samples_lost_budget=True
        fresh_hours+=int(previous==truth(trace,t))
        total_hours+=1
        t+=QUANTUM
    if requests>BUDGET or len(samples)!=requests:
        raise AssertionError("synthetic request conservation failure")
    return {"trace":trace.name,"policy":mode,"requests":requests,
            "true_change_events":len(trace.changes),"observed_changed_pairs":changes_seen,
            "fresh_hour_fraction":round(fresh_hours/total_hours,6),
            "stale_hours":total_hours-fresh_hours,"budget_prevented_due_fetch":samples_lost_budget,
            "sample_digest":hashlib.sha256(json.dumps([(x.at,x.digest) for x in samples],
                                  separators=(",",":")).encode()).hexdigest()}


def benchmark():
    results=[simulate(trace,policy) for trace in traces()
             for policy in ("fixed_budget","multiplicative","posterior")]
    if results!=[simulate(trace,policy) for trace in traces()
                 for policy in ("fixed_budget","multiplicative","posterior")]:
        raise AssertionError("non-deterministic synthetic revisit results")
    return {"schema":"skeleton.dragon.revisit-benchmark.v1","source":"synthetic_temporal_traces",
            "horizon_days":60,"request_budget_per_trace":BUDGET,"external_network_used":False,
            "external_competitors_executed":[],"superiority_claimed":False,"results":results}


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--output",type=Path)
    args=cli.parse_args()
    report=json.dumps(benchmark(),sort_keys=True,indent=2,allow_nan=False)+"\n"
    if args.output:
        args.output.write_text(report,encoding="utf-8")
    else:
        print(report,end="")


if __name__=="__main__":
    main()
