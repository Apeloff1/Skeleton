"""Lifecycle of an automatic native flight worker with explicit drain holds."""
from __future__ import annotations
from threading import RLock
from .contracts import DaemonPolicy,DaemonBusy,DaemonError,DaemonHeld
from .status import DaemonStatus
from .preflight import inspect as preflight
from .loop import WorkLoop

class InferenceDaemon:
    """Automatically services queued requests using a SINGLE model caller.

    The backend may be non-reentrant. We never spin up multiple local inference
    threads under a single native model. Operators can provision independent
    worker processes, each with its own loaded model, using the shared lease DB.
    """
    def __init__(self,application,*,policy:DaemonPolicy|None=None):
        self.app=application
        self.policy=policy or DaemonPolicy()
        if not isinstance(self.policy,DaemonPolicy):raise DaemonError('policy required')
        self._lock=RLock()
        self.status=DaemonStatus()
        self._loop=None
        self._proof=None

    def start(self)->dict:
        with self._lock:
            if self._loop is not None or self.status.snapshot()['phase']!='new':
                raise DaemonError('supervisor can only start once')
            self.status.set_phase('starting')
            try:
                self._proof=preflight(self.app,self.policy)
                loop=WorkLoop(self.app.worker,self.status,self.policy)
                self._loop=loop
                self.status.set_phase('running')
                loop.start()
            except BaseException as exc:
                self.status.fail(exc)
                raise
            return self._proof.copy()

    def notify(self)->bool:
        with self._lock:
            if self._loop is None:return False
            if self.status.snapshot()['phase']!='running':return False
            self._loop.notify();return True

    def accepting(self)->bool:
        """Observe only worker availability, never manufacture approval.

        Submission is forbidden once the worker has faulted, stopped, is
        draining, or has exceeded the observational stall threshold. The
        persistent operator paused mode still permits bounded queueing.
        """
        status=self.snapshot()
        return status['phase']=='running' and not status['stall_observed']

    def snapshot(self)->dict:
        result=self.status.snapshot(stall_ms=self.policy.health_stall_ms)
        # No model health or benchmark claim is inferred from scheduler state.
        return result

    def stop(self,*,timeout_ms:int|None=None)->dict:
        timeout=self.policy.shutdown_grace_ms if timeout_ms is None else timeout_ms
        if type(timeout)is not int or not 1<=timeout<=600000:
            raise DaemonError('invalid bounded shutdown deadline')
        with self._lock:
            phase=self.status.snapshot()['phase']
            if phase=='new':
                self.status.set_phase('stopped');return self.snapshot()
            if phase=='starting':raise DaemonBusy('supervisor is starting')
            if phase=='stopped':return self.snapshot()
            if phase!='held':self.status.set_phase('draining')
            loop=self._loop
            if loop is not None:loop.request_stop()
        if loop is not None and not loop.join(timeout/1000):
            # Caller's state must remain open while inference is still running.
            # SIGKILL is an explicit process-level operator decision, not an API.
            raise DaemonBusy('native inference still active; state must remain open')
        if self.status.snapshot()['phase']!='held':self.status.set_phase('stopped')
        return self.snapshot()

    def close(self)->dict:
        """Fully drain before returning ownership of the model and database."""
        while True:
            try:return self.stop()
            except DaemonBusy:
                # Never abandon a live noninterruptible native call; allow the
                # existing lease heartbeat to continue until it resolves.
                continue

    def __enter__(self):
        self.start();return self

    def __exit__(self,*_):
        self.close()
