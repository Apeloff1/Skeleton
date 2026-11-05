"""Composed startup and runtime readiness without model-quality exaggeration."""
from __future__ import annotations
from .. import controls,watchdog
from .contracts import DaemonError

def assess(daemon,*,max_jobs:int=2048)->dict:
    if type(max_jobs)is not int or not 1<=max_jobs<=4096:
        raise DaemonError('readiness inspection limit invalid')
    snapshot=daemon.snapshot()
    with daemon.app.ledger.db.snapshot() as conn:
        mode=controls.mode(conn)
    watch=watchdog.report(daemon.app.ledger,limit=max_jobs)
    issue= 'failed-worker' if snapshot['phase']=='held' else (
         'manual-drain' if snapshot['phase'] in ('draining','stopped') else (
         'operator-paused' if mode=='paused' else (
         'stale-lease' if watch['stale_count'] else (
         'inference-not-started' if snapshot['phase'] in ('new','starting') else (
         'stalled-native-inference' if snapshot['stall_observed'] else None)))))
    return {'schema':'skeleton.ai.native-readiness.v1','serving':issue is None,
            'reason':issue,'phase':snapshot['phase'],'flight_mode':mode,
            'stale_jobs':watch['stale_count'],
            'model_generation_quality':'requires-independent-real-model-probe'}
