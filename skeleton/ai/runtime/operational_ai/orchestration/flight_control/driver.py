"""Worker-facing adapter for real synchronous native inference with custody.

The runner does not promise exactly-once GPU compute, which is impossible to
prove over a crash boundary. It DOES prevent blind re-execution of uncertain
requests and exactly-once durable publication of completed receipts.
"""
from __future__ import annotations
from dataclasses import dataclass
from threading import Event,Thread,RLock
import time
from .contracts import FlightConflict,FlightError,FlightBusy,Ticket


@dataclass(frozen=True,slots=True)
class WorkerResult:
    job_id:str
    state:str
    revision:int|None
    recovered:bool


class _Pulse:
    def __init__(self,ledger,ticket):
        self.ledger=ledger;self.ticket=ticket;self.stop=Event();self.lock=RLock()
        self.error=None;self.thread=None

    def __enter__(self):
        self.thread=Thread(target=self._loop,name='ai-flight-heartbeat',daemon=True)
        self.thread.start()
        return self

    def _loop(self):
        interval=max(.02,self.ledger.settings.lease_ms/3000)
        while not self.stop.wait(interval):
            with self.lock:
                try:self.ticket=self.ledger.heartbeat(self.ticket)
                except BaseException as exc:
                    self.error=exc;self.stop.set();return

    def finish(self)->Ticket:
        self.stop.set();self.thread.join(timeout=5)
        if self.thread.is_alive():raise FlightConflict('flight heartbeat did not terminate')
        with self.lock:
            if self.error is not None:raise FlightConflict('flight heartbeat lost custody') from self.error
            return self.ticket

    def __exit__(self,*_):
        self.stop.set();self.thread.join(timeout=5)


class NativeFlightWorker:
    def __init__(self,ledger,spine,worker_id:str):
        from ..execution_spine.contracts import identifier
        identifier(worker_id,'worker')
        if spine.identity!=ledger.identity:raise FlightConflict('worker model identity mismatch')
        self.ledger=ledger;self.spine=spine;self.worker_id=worker_id

    def run_one(self)->WorkerResult|None:
        ticket=self.ledger.claim(self.worker_id)
        if ticket is None:return None
        try:
            self.ledger.start(ticket)
            spec=self.ledger.request_for(ticket.job_id)
            # Existing authoritative receipt could result from an earlier writer
            # entering via another public path. Do not burn another model cycle.
            replay=self.spine.replay(spec.session,spec.request_id,spec.prompt,
                                     seed=spec.seed,temperature=spec.temperature)
            with _Pulse(self.ledger,ticket) as pulse:
                receipt=replay if replay is not None else self.spine.turn(
                    spec.session,spec.request_id,spec.prompt,seed=spec.seed,
                    temperature=spec.temperature)
                fresh=pulse.finish()
            completed=self.ledger.finish(fresh,receipt,spine=self.spine)
            return WorkerResult(ticket.job_id,'completed',completed['result']['revision'],replay is not None)
        except BaseException as exc:
            # Never leak model prompts or provider exceptions into audit events.
            # An expired fence is left for operator reconciliation.
            try:self.ledger.fail(ticket,type(exc).__name__[:64])
            except FlightError:pass
            if isinstance(exc,FlightBusy):
                # Once the claim has been acquired, capacity conflicts are
                # not merely idle polling. This ticket may now be held and
                # must stop automatic dispatch until operator review.
                raise FlightConflict('claimed task failed before native execution') from exc
            raise

    def drain(self,*,maximum:int=32)->tuple[WorkerResult,...]:
        if type(maximum)is not int or not 1<=maximum<=256:
            raise FlightConflict('invalid finite worker drain limit')
        outcomes=[]
        for _ in range(maximum):
            result=self.run_one()
            if result is None:break
            outcomes.append(result)
        return tuple(outcomes)
