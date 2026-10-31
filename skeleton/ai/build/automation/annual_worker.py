"""Bounded, verifier-gated production quantum for Jeeves, Builder and Dragon.

An app/OS process supervisor owns scheduling and restarts. This runner does
ONE unit of work per invocation. The supplied backend handler must persist
its canonical content under the provided stable idempotency key, and external
verification must establish that its evidence actually exists. A stale lease
must not commit, even when a worker returns after months of suspension.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import time
from typing import Callable

from .annual_production import (
    AnnualProductionStore, Claim, ProductionConflict, ProductionState,
    _digest,
)

@dataclass(frozen=True)
class WorkQuantum:
    production_id: str
    system: str
    sequence: int
    idempotency_key: str
    last_checkpoint_digest: str | None
    last_receipt_digest: str | None
    claim: Claim
    heartbeat: Callable[[int], Claim]

@dataclass(frozen=True)
class VerifiedWork:
    state_digest: str
    evidence_digest: str
    terminal: str | None = None
    terminal_evidence_digest: str | None = None

@dataclass(frozen=True)
class QuantumReport:
    state: str
    production_id: str
    sequence: int
    receipt_digest: str | None
    terminal: str | None

ExternalWorker = Callable[[WorkQuantum], VerifiedWork]
ExternalVerifier = Callable[[WorkQuantum, VerifiedWork], bool]


class AnnualWorkRunner:
    """A backend-provided worker + verifier, not an independent AI model."""

    def __init__(self, store: AnnualProductionStore, *, system: str,
                 worker: ExternalWorker, verify: ExternalVerifier,
                 clock: Callable[[], float] = time.time):
        if system not in {"jeeves", "builder", "dragon"}:
            raise ValueError("unknown production system")
        if not callable(worker) or not callable(verify):
            raise ValueError("canonical worker and evidence verifier are required")
        self.store = store
        self.system = system
        self.worker = worker
        self.verify = verify
        self.clock = clock

    def run_one(self, production_id: str, *, owner: str, authority_digest: str,
                lease_seconds: int = 120) -> QuantumReport:
        started = self.clock()
        before = self.store.read(production_id)
        if before.system != self.system:
            raise ProductionConflict("runner not authorized for this subsystem")
        # Ensure the saved head and full ancestry have not been tampered with.
        self.store.verify_chain(production_id)
        self.store.verify_authority_chain(production_id)
        claim = self.store.claim(production_id, worker=owner,
                                 authority_digest=authority_digest, now=started,
                                 lease_seconds=lease_seconds)
        stable = sha256(
            (production_id + ":" + str(before.sequence + 1)).encode("utf-8")
        ).hexdigest()
        quantum = WorkQuantum(
            production_id, self.system, before.sequence + 1,
            "annual-quantum-sha256:" + stable,
            before.checkpoint_digest, before.last_receipt_digest, claim,
            lambda ttl: self.store.heartbeat(claim, now=self.clock(), lease_seconds=ttl),
        )
        try:
            output = self.worker(quantum)
            if not isinstance(output, VerifiedWork):
                raise ValueError("canonical worker returned invalid receipt")
            _digest(output.state_digest, "state")
            _digest(output.evidence_digest, "evidence")
            if output.terminal is not None:
                if output.terminal not in {"completed", "failed", "cancelled"}:
                    raise ValueError("invalid terminal outcome")
                _digest(output.terminal_evidence_digest, "terminal evidence")
            if self.verify(quantum, output) is not True:
                raise PermissionError("canonical evidence not verified")
        except BaseException:
            # Do not immediately requeue an ambiguous side effect: the old
            # lease expires naturally, and a new worker uses the SAME stable
            # idempotency key to inspect/reconcile that canonical operation.
            raise
        receipt = self.store.checkpoint(
            claim, sequence=quantum.sequence,
            state_digest=output.state_digest, evidence_digest=output.evidence_digest,
            now=self.clock(),
        )
        if output.terminal is not None:
            final = self.store.terminal(
                claim, state=output.terminal,
                verified_evidence_digest=output.terminal_evidence_digest or "",
                verify_evidence=lambda _p, _s, _d: True,  # already verified above
                now=self.clock(),
            )
            return QuantumReport("terminal", final.production_id, final.sequence,
                                 receipt, output.terminal)
        # Minimum one-second yield lets other due productions make progress
        # before this fast worker is admitted for another quantum.
        waiting = self.store.release(claim, now=self.clock(), retry_seconds=1)
        return QuantumReport("checkpointed", waiting.production_id,
                             waiting.sequence, receipt, None)
