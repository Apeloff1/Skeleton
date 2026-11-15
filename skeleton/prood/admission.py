"""Connect deterministic Prood plans to explicit durable work admission.

Planning still performs no execution. Queued orders are bound to plan, phase,
role, and seat; later phases depend on every worker in the previous phase.
The app must authorize each claim and route it to a real worker owner.
"""
from __future__ import annotations

from dataclasses import dataclass

from skeleton.frontier.durable_work import DurableWorkJournal, WorkOrder, WorkStatus, work_identity
from skeleton.prood.swarm_planner import plan_build


@dataclass(frozen=True, slots=True)
class ProodAdmission:
    plan_hash: str
    work: tuple[WorkStatus, ...]

    @property
    def worker_count(self) -> int:
        return len(self.work)

    @property
    def execution_verified(self) -> bool:
        # A status receipt cannot independently qualify the runtime.
        return False


def build_orders(scope: str, *, build_id: str,
                 phases: list[str] | None = None, seed: int = 0,
                 platoon_size: int = 5, game_ctx: dict | None = None) -> tuple[str, tuple[WorkOrder, ...]]:
    """Reconstruct the exact admission orders for read-only verification."""
    plan = plan_build(build_id, phases=phases, seed=seed,
                      platoon_size=platoon_size, game_ctx=game_ctx)
    orders = []
    previous_phase: tuple[str, ...] = ()
    for node in plan["nodes"]:
        current = []
        for worker in node["workers"]:
            identity = [plan["plan_hash"], node["phase_id"], worker["code"]]
            wid = work_identity(scope, "prood.worker", identity)
            payload = {
                "schema": "prood.worker.v1", "plan_hash": plan["plan_hash"],
                "build_id": plan["build_id"], "context_digest": plan["context_digest"],
                "phase": node["phase_id"], "worker": worker["code"],
                "role": worker["category"], "seat": worker["team_seat"],
                "seed": plan["seed"], "execution_verified": False,
            }
            current.append(wid)
            orders.append(WorkOrder(wid, "prood.worker", payload, previous_phase))
        previous_phase = tuple(current)
    return plan["plan_hash"], tuple(orders)


def admit_build(journal: DurableWorkJournal, *, build_id: str,
                phases: list[str] | None = None, seed: int = 0,
                platoon_size: int = 5, game_ctx: dict | None = None) -> ProodAdmission:
    if type(journal) is not DurableWorkJournal:
        raise TypeError("canonical app-owned work journal required")
    plan_hash, orders = build_orders(journal.scope, build_id=build_id, phases=phases,
                                     seed=seed, platoon_size=platoon_size, game_ctx=game_ctx)
    return ProodAdmission(plan_hash, journal.submit(orders))
