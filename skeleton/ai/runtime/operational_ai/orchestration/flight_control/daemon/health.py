"""Authenticated daemon status is observational, not a quality certification."""
from __future__ import annotations

def public_health(daemon)->dict:
    status=daemon.snapshot()
    allowed={'schema','phase','completed_jobs','idle_polls','capacity_polls',
             'failures','last_error_type','active_inference',
             'age_since_progress_ms','stall_observed','uptime_ms','readiness'}
    if set(status)!=allowed:raise ValueError('daemon health schema mismatch')
    from .readiness import assess
    # A running thread is not ready if operator admission is paused, its lease
    # inventory is stale, or the worker has stalled. Never report green merely
    # because the socket is accepting requests.
    return {'supervisor':status,'admission':assess(daemon)}
