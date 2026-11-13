"""Fair bounded single-pass orchestration across annual production lanes.

A real process supervisor (systemd, Kubernetes, Windows service or scheduled
operator) must invoke one sweep and restart it after host failure. We do NOT
schedule unowned background work or bypass Jeeves, Builder, Dragon permission
checks. Claim/lease/checkpoint durable authority belongs to AnnualWorkRunner.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

from .annual_production import AnnualProductionStore, ProductionConflict
from .annual_worker import AnnualWorkRunner, QuantumReport

AuthorityResolver = Callable[[str, str], str]


@dataclass(frozen=True)
class AnnualSweepItem:
    production_id: str
    system: str
    status: str
    sequence: int


@dataclass(frozen=True)
class AnnualSweepReport:
    examined: int
    checkpointed: int
    terminal: int
    deferred: int
    errors: tuple[AnnualSweepItem, ...]


class AnnualProductionSupervisor:
    """One bounded admission pass, at most one quantum per production ID."""

    def __init__(self, store: AnnualProductionStore,
                 runners: Mapping[str, AnnualWorkRunner],
                 authority: AuthorityResolver):
        if not callable(authority):
            raise ValueError("trusted current grant resolver required")
        if set(runners) != {"jeeves", "builder", "dragon"}:
            raise ValueError("all three production planes must be bound")
        if any(r.system != subsystem or r.store is not store
               for subsystem, r in runners.items()):
            raise ValueError("runner system/authority mismatch")
        self.store = store
        self.runners = dict(runners)
        self.authority = authority

    def sweep(self, *, owner: str, now: float, limit: int = 8) -> AnnualSweepReport:
        # The due query rejects invalid limits and ignores grant-expired or
        # actively leased rows. The bounded snapshot avoids starvation from
        # a constantly re-due very fast job within a single pass.
        due = self.store.due(now=now, limit=limit)
        successes, terminal, deferred = 0, 0, 0
        errors: list[AnnualSweepItem] = []
        for row in due:
            try:
                grant = self.authority(row.production_id, row.system)
                report: QuantumReport = self.runners[row.system].run_one(
                    row.production_id, owner=owner, authority_digest=grant,
                )
                if report.state == "terminal":
                    terminal += 1
                else:
                    successes += 1
            except (PermissionError, ProductionConflict, ValueError) as exc:
                # Fail closed; no internal exception messages or signed grant
                # materials are persisted in the audit report.
                errors.append(AnnualSweepItem(
                    row.production_id, row.system, type(exc).__name__,
                    row.sequence,
                ))
            except Exception as exc:
                # Unexpected worker exceptions leave their lease in place for
                # operator reconciliation after expiry. Do not tight-loop.
                deferred += 1
                errors.append(AnnualSweepItem(
                    row.production_id, row.system,
                    "unverified_" + type(exc).__name__, row.sequence,
                ))
        return AnnualSweepReport(len(due), successes, terminal,
                                 deferred, tuple(errors))
