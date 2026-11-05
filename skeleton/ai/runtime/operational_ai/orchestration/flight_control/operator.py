"""Privileged operator entrypoints, separate from model and user-request APIs."""
from __future__ import annotations
from dataclasses import dataclass
from .contracts import FlightConflict
from . import controls,doctor,recovery,watchdog,proof,batch


@dataclass(slots=True)
class FlightOperator:
    ledger:object
    spine:object

    def __post_init__(self):
        if self.spine.identity!=self.ledger.identity:
            raise FlightConflict('operator principal/model binding mismatch')

    def diagnose(self,*,max_jobs:int=2048)->dict:
        # Strictly read-only (except SQLite's read-side journal behavior).
        return {'integrity':doctor.inspect(self.ledger,max_jobs=max_jobs),
                'watchdog':watchdog.report(self.ledger,limit=max_jobs),
                'proof':proof.export(self.ledger,limit=max_jobs)['manifest_sha256']}

    def pause(self,*,approved:bool=False)->dict:
        return controls.configure(self.ledger,'paused',approved=approved)

    def resume(self,*,approved:bool=False)->dict:
        return controls.configure(self.ledger,'running',approved=approved)

    def recover(self,*,approved:bool=False,limit:int=256)->dict:
        return recovery.reconcile(self.ledger,self.spine,approved=approved,limit=limit)

    def enqueue(self,specs,*,maximum:int=128)->tuple[dict,...]:
        return batch.submit_many(self.ledger,specs,maximum=maximum)
