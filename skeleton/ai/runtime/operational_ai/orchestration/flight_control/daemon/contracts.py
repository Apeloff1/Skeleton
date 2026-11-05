"""Bounded, explicit runtime constraints for the native inference daemon."""
from __future__ import annotations
from dataclasses import dataclass

class DaemonError(RuntimeError):
    """Daemon contract or lifecycle violation."""
class DaemonBusy(DaemonError):
    """Non-interruptible native inference is still running; do not tear it down."""
class DaemonHeld(DaemonError):
    """An integrity or model-execution failure requires independent review."""

@dataclass(frozen=True,slots=True)
class DaemonPolicy:
    poll_ms:int=200
    startup_max_jobs:int=2048
    startup_max_events_per_job:int=4096
    shutdown_grace_ms:int=120000
    health_stall_ms:int=120000

    def __post_init__(self)->None:
        for name,lower,upper in (
            ('poll_ms',20,10000),('startup_max_jobs',1,4096),
            ('startup_max_events_per_job',1,4096),
            ('shutdown_grace_ms',100,600000),
            ('health_stall_ms',1000,600000)):
            value=getattr(self,name)
            if type(value)is not int or not lower<=value<=upper:
                raise DaemonError('invalid bounded daemon policy: '+name)
