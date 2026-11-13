"""Private, bounded, read-only queue telemetry derived from durable timestamps.

No prompts, model outputs or identifying job/session IDs are exported.
"""
from __future__ import annotations
from collections import Counter
from math import ceil
from .contracts import DaemonError

def _percentile(samples:list[int],quantile:int)->int|None:
    if not samples:return None
    samples.sort()
    return samples[max(0,ceil((len(samples)*quantile)/100)-1)]

def snapshot(ledger,*,maximum:int=2048)->dict:
    if type(maximum)is not int or not 1<=maximum<=4096:
        raise DaemonError('telemetry inventory must be bounded')
    with ledger.db.snapshot() as conn:
        rows=conn.execute("""SELECT state, created_ns,started_ns,finished_ns,cancel_requested
            FROM ai_flight_jobs WHERE principal=? ORDER BY created_ns,job_id LIMIT ?""",
            (ledger.identity.key(),maximum+1)).fetchall()
    if len(rows)>maximum:
        raise DaemonError('telemetry review ceiling exceeded')
    counts=Counter();wait=[];compute=[];end=[];cancelled_running=0
    for state,created,started,finished,cancel in rows:
        if (state not in ('queued','claimed','running','completed','held','cancelled') or
            type(created)is not int or created<=0 or
            (started is not None and (type(started)is not int or started<created)) or
            (finished is not None and (type(finished)is not int or finished<created))):
            raise DaemonError('invalid durable telemetry timestamp or state')
        counts[state]+=1
        if state=='completed' and (started is None or finished is None or finished<started):
            raise DaemonError('completed inference is missing a consistent interval')
        if started is not None:
            wait.append((started-created)//1_000_000)
        if started is not None and finished is not None:
            if finished<started:raise DaemonError('negative inference duration')
            compute.append((finished-started)//1_000_000)
            end.append((finished-created)//1_000_000)
        if cancel and state=='running':cancelled_running+=1
    return {'schema':'skeleton.ai.flight-telemetry.v1','status':'derived-from-durable-records',
            'jobs':len(rows),'counts':{k:counts[k] for k in ('queued','claimed','running','completed','held','cancelled')},
            'queue_wait_ms_p50':_percentile(wait,50),'queue_wait_ms_p95':_percentile(wait,95),
            'inference_ms_p50':_percentile(compute,50),'inference_ms_p95':_percentile(compute,95),
            'end_to_end_ms_p95':_percentile(end,95),'cancel_requested_running':cancelled_running,
            'model_quality':'unassessed','notes':'wall-clock intervals, not latency SLA certification'}
