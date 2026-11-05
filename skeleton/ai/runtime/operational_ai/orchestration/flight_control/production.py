"""Strictly real GGUF-backed, owner-bound flight-control runtime activation."""
from __future__ import annotations
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator
from .contracts import FlightPolicy, FlightConflict
from .ledger import FlightLedger
from .driver import NativeFlightWorker
from .operator import FlightOperator


@dataclass(frozen=True,slots=True)
class FlightApplication:
    """A live, verified model + durable execution and operator control."""
    spine:object
    ledger:FlightLedger
    worker:NativeFlightWorker
    operator:FlightOperator


@contextmanager
def activate_flight(*,model_root:str|Path,state_dir:str|Path,
                    tenant:str,subject:str,worker_id:str,
                    n_ctx:int=8192,max_new_tokens:int=512,n_threads:int=4,
                    gpu_layers:int=0,settings:FlightPolicy|None=None,
                    isolate_native:bool=False,capacity_root:Path|None=None,
                    capacity_slots:int=1,capacity_budget_bytes:int=8_000_000_000)->Iterator[FlightApplication]:
    """No local demo/fake fallback; startup activates an approved native model.

    The existing production startup is authoritative for principal binding,
    private directory custody and model checkpoint admission. This layer adds
    only durable queue and worker, not a new model implementation.
    """
    from ...deployment.production.startup import activate
    stack,supervised=activate(model_root=model_root,state_dir=state_dir,
         tenant=tenant,subject=subject,n_ctx=n_ctx,
         max_new_tokens=max_new_tokens,n_threads=n_threads,gpu_layers=gpu_layers,
         isolated=isolate_native,capacity_root=capacity_root,
         capacity_slots=capacity_slots,capacity_budget_bytes=capacity_budget_bytes)
    with stack:
        spine=supervised.spine
        ledger=FlightLedger(spine.db,spine.identity,settings=settings)
        worker=NativeFlightWorker(ledger,spine,worker_id)
        operator=FlightOperator(ledger,spine)
        yield FlightApplication(spine,ledger,worker,operator)
