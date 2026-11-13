"""One native model caller per daemon; no silent retries after failures.

This thread is intentionally non-daemon: process teardown cannot close the
GGUF backend or SQLite authority while model computation is still active.
"""
from __future__ import annotations
from threading import Event,Thread
from ..contracts import FlightBusy

class WorkLoop:
    def __init__(self,worker,status,policy):
        self.worker=worker;self.status=status;self.policy=policy
        self.stop_requested=Event();self.wake=Event()
        self.thread=Thread(target=self._run,name='skeleton-native-inference',daemon=False)

    def start(self):self.thread.start()

    def notify(self):
        self.wake.set()

    def request_stop(self):
        self.stop_requested.set();self.wake.set()

    def join(self,seconds:float|None):
        self.thread.join(timeout=seconds)
        return not self.thread.is_alive()

    def _run(self):
        while not self.stop_requested.is_set():
            try:
                # All queue transitions, lease renewal and exact-head receipt
                # checks are owned by NativeFlightWorker and FlightLedger.
                self.status.started_job()
                outcome=self.worker.run_one()
            except FlightBusy:
                self.status.no_active();self.status.idle(capacity=True)
                self.wake.wait(self.policy.poll_ms/1000)
                self.wake.clear()
                continue
            except BaseException as exc:
                # A started model can have executed before any exception. Do NOT
                # retry automatically; user/operator must inspect durable ledger.
                self.status.fail(exc)
                self.stop_requested.set()
                return
            self.status.no_active()
            if outcome is None:
                self.status.idle()
                self.wake.wait(self.policy.poll_ms/1000)
                self.wake.clear()
                continue
            if outcome.state!='completed':
                self.status.fail(RuntimeError('noncompleted native work outcome'))
                self.stop_requested.set()
                return
            self.status.completed_job(outcome.job_id)
        self.status.set_phase('stopped')
