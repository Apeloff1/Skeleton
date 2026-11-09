"""High-level Jeeves control plane.

This module composes the provider-neutral router, bounded execution kernel,
episodic memory, LiveSession isolation, and evolve-first adoption policy into one
auditable workflow. It deliberately does not call an LLM or expose HTTP routes;
callers supply candidate world operations and measurements, while this layer
decides how they may be evaluated and adopted.

Ordinary evolution can be configured for automatic adoption after metric gates.
Broad mutation is always held for explicit approval, even when its metrics pass.
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from core.evolution_policy import ChangeMode, EvolutionPolicy, default_jeeves_policy
from core.jeeves_execution_kernel import (
    CapabilityRejected,
    JeevesRuntime,
    Priority,
    get_default_runtime,
)
from core.jeeves_memory import MemoryBank
from core.live_session import AdoptionResult, LiveSession, SessionEvaluation, SessionState
from core.model_router import ModelEndpoint, ModelRouter, RouteDecision, RouteRequest
from core.world_graph import PatchOp, WorldGraph


class ControlPlaneError(RuntimeError):
    """Base control-plane failure."""


class ApprovalRequired(ControlPlaneError):
    """Raised when a pending mutation requires explicit approval."""


class UnknownPendingEvolution(ControlPlaneError):
    """Raised for unknown or already-resolved pending sessions."""


@dataclass(frozen=True)
class PendingEvolutionSummary:
    session_id: str
    mode: ChangeMode
    agent_id: str
    candidate_hash: str
    gain: float
    created_at: float
    selected_endpoint_id: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "mode": self.mode.value,
            "agent_id": self.agent_id,
            "candidate_hash": self.candidate_hash,
            "gain": round(self.gain, 8),
            "created_at": self.created_at,
            "selected_endpoint_id": self.selected_endpoint_id,
        }


@dataclass(frozen=True)
class WorldEvolutionOutcome:
    run_id: str
    status: str
    session_id: str
    route: RouteDecision | None
    evaluation: SessionEvaluation
    adoption: AdoptionResult | None
    execution: Mapping[str, Any]
    evidence: tuple[Mapping[str, Any], ...]
    memory_ids: tuple[str, ...]

    @property
    def accepted(self) -> bool:
        return self.evaluation.decision.accepted

    @property
    def adopted(self) -> bool:
        return self.adoption is not None

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "session_id": self.session_id,
            "accepted": self.accepted,
            "adopted": self.adopted,
            "route": self.route.as_dict() if self.route else None,
            "evaluation": self.evaluation.as_dict(),
            "adoption": self.adoption.as_dict() if self.adoption else None,
            "execution": dict(self.execution),
            "evidence": [dict(row) for row in self.evidence],
            "memory_ids": list(self.memory_ids),
        }


@dataclass(frozen=True)
class PendingAdoptionOutcome:
    run_id: str
    session_id: str
    adoption: AdoptionResult
    execution: Mapping[str, Any]
    evidence: tuple[Mapping[str, Any], ...]
    memory_ids: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "session_id": self.session_id,
            "adoption": self.adoption.as_dict(),
            "execution": dict(self.execution),
            "evidence": [dict(row) for row in self.evidence],
            "memory_ids": list(self.memory_ids),
        }


@dataclass
class _PendingEvolution:
    session: LiveSession
    evaluation: SessionEvaluation
    mode: ChangeMode
    agent_id: str
    route: RouteDecision | None
    evidence_ids: tuple[str, ...]
    created_at: float

    def summary(self) -> PendingEvolutionSummary:
        return PendingEvolutionSummary(
            session_id=self.session.session_id,
            mode=self.mode,
            agent_id=self.agent_id,
            candidate_hash=self.evaluation.candidate_hash,
            gain=self.evaluation.decision.gain,
            created_at=self.created_at,
            selected_endpoint_id=(
                self.route.selected.endpoint_id if self.route is not None else None
            ),
        )


class JeevesControlPlane:
    """Compose routing, execution, memory, experimentation, and adoption policy."""

    def __init__(
        self,
        *,
        runtime: JeevesRuntime | None = None,
        router: ModelRouter | None = None,
        memory: MemoryBank | None = None,
        policy: EvolutionPolicy | None = None,
        max_pending: int = 128,
    ) -> None:
        if max_pending < 1:
            raise ValueError("max_pending must be >= 1")
        self.runtime = runtime or get_default_runtime()
        self.router = router or ModelRouter()
        self.memory = memory or MemoryBank()
        self.policy = policy or default_jeeves_policy()
        self.max_pending = int(max_pending)
        self._pending: dict[str, _PendingEvolution] = {}
        self._pending_order: deque[str] = deque()
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Model routing / telemetry
    # ------------------------------------------------------------------
    def register_model(self, endpoint: ModelEndpoint, *, replace: bool = False) -> None:
        self.router.register(endpoint, replace=replace)

    def observe_model(
        self,
        endpoint_id: str,
        *,
        ok: bool,
        quality: float | None = None,
        latency_ms: float | None = None,
        cost: float | None = None,
        observed_at: float | None = None,
    ) -> None:
        self.router.observe(
            endpoint_id,
            ok=ok,
            quality=quality,
            latency_ms=latency_ms,
            cost=cost,
            observed_at=observed_at,
        )

    def route(self, request: RouteRequest) -> RouteDecision:
        return self.router.route(request)

    # ------------------------------------------------------------------
    # Pending candidate lifecycle
    # ------------------------------------------------------------------
    def _remember(
        self,
        *,
        agent_id: str,
        run_id: str,
        status: str,
        evaluation: SessionEvaluation,
        route: RouteDecision | None,
        adopted: bool,
    ) -> tuple[str, ...]:
        """Record compact deterministic outcome memory; never expose raw prompts."""
        selected = route.selected.endpoint_id if route is not None else None
        payload = {
            "run_id": run_id,
            "status": status,
            "session_id": evaluation.session_id,
            "candidate_hash": evaluation.candidate_hash,
            "accepted": evaluation.decision.accepted,
            "adopted": adopted,
            "gain": round(evaluation.decision.gain, 8),
            "violations": list(evaluation.decision.violations),
            "selected_endpoint_id": selected,
        }
        episode = self.memory.remember(
            agent_id,
            json.dumps(payload, sort_keys=True, separators=(",", ":")),
            kind="evolution",
            importance=0.85 if adopted else 0.65,
            tags=("world", "evolution", status),
        )
        ids = [episode.memory_id]

        if evaluation.decision.accepted:
            insight = (
                f"candidate {evaluation.candidate_hash} cleared evolution policy "
                f"with gain {evaluation.decision.gain:.6f}; adopted={adopted}"
            )
        else:
            violations = ", ".join(evaluation.decision.violations[:4]) or "gain threshold"
            insight = (
                f"candidate {evaluation.candidate_hash} was rejected by evolution policy: "
                f"{violations}"
            )
        reflection = self.memory.remember_reflection(
            agent_id,
            insight,
            [episode.memory_id],
            importance=0.9 if adopted else 0.75,
            tags=("world", "policy", "reflection"),
        )
        ids.append(reflection.memory_id)
        return tuple(ids)

    def _store_pending(self, pending: _PendingEvolution) -> None:
        session_id = pending.session.session_id
        with self._lock:
            if session_id in self._pending:
                raise ControlPlaneError(f"duplicate pending session: {session_id}")
            while len(self._pending) >= self.max_pending and self._pending_order:
                oldest_id = self._pending_order.popleft()
                oldest = self._pending.pop(oldest_id, None)
                if oldest is not None and oldest.session.state is SessionState.OPEN:
                    oldest.session.discard()
            self._pending[session_id] = pending
            self._pending_order.append(session_id)

    def _pop_pending(self, session_id: str) -> _PendingEvolution:
        with self._lock:
            pending = self._pending.pop(session_id, None)
            if pending is None:
                raise UnknownPendingEvolution(session_id)
            try:
                self._pending_order.remove(session_id)
            except ValueError:
                pass
            return pending

    def _get_pending(self, session_id: str) -> _PendingEvolution:
        with self._lock:
            pending = self._pending.get(session_id)
            if pending is None:
                raise UnknownPendingEvolution(session_id)
            return pending

    def pending(self) -> tuple[PendingEvolutionSummary, ...]:
        with self._lock:
            rows = [
                self._pending[session_id].summary()
                for session_id in self._pending_order
                if session_id in self._pending
            ]
        return tuple(rows)

    def discard_pending(self, session_id: str) -> dict[str, Any]:
        pending = self._pop_pending(session_id)
        if pending.session.state is SessionState.OPEN:
            return pending.session.discard()
        return pending.session.snapshot()

    # ------------------------------------------------------------------
    # World evolution
    # ------------------------------------------------------------------
    def evolve_world(
        self,
        canonical: WorldGraph,
        operations: Sequence[PatchOp | Mapping[str, Any]],
        *,
        baseline_metrics: Mapping[str, float],
        candidate_metrics: Mapping[str, float],
        evidence_ids: Sequence[str],
        route_request: RouteRequest | None = None,
        agent_id: str = "jeeves",
        mode: ChangeMode | str = ChangeMode.EVOLVE,
        auto_adopt: bool = True,
        mutation_approved: bool = False,
        priority: Priority | str | int = Priority.NORMAL,
        max_steps: int | None = 12,
        max_seconds: float | None = 30.0,
        admission_timeout: float | None = 5.0,
    ) -> WorldEvolutionOutcome:
        """Evaluate one candidate world change under bounded execution.

        Rejected candidates never touch canonical state. Accepted ordinary
        evolution can auto-adopt. Accepted broad mutation remains pending until
        ``mutation_approved`` is true or :meth:`adopt_pending` is called later
        with explicit approval.
        """
        if not isinstance(canonical, WorldGraph):
            raise TypeError("canonical must be a WorldGraph")
        operations = tuple(operations)
        evidence_ids = tuple(str(item).strip() for item in evidence_ids if str(item).strip())
        agent_id = str(agent_id).strip() or "jeeves"
        mode = ChangeMode(mode)
        run_id = uuid.uuid4().hex[:16]
        route: RouteDecision | None = None
        adoption: AdoptionResult | None = None
        status = "started"
        memory_ids: tuple[str, ...] = ()

        with self.runtime.execution(
            run_id=run_id,
            build_id=canonical.semantic_hash(),
            priority=priority,
            max_steps=max_steps,
            max_seconds=max_seconds,
            admission_timeout=admission_timeout,
        ) as execution:
            if route_request is not None:
                execution.checkpoint("jeeves.route", consume_step=True)
                route = self.router.route(route_request)
                execution.record(
                    "jeeves.route.selected",
                    {
                        "endpoint_id": route.selected.endpoint_id,
                        "fallbacks": list(route.fallback_endpoint_ids),
                        "rejected": len(route.rejected),
                    },
                )

            execution.checkpoint("jeeves.session.open", consume_step=True)
            session = LiveSession(canonical, author=agent_id)

            execution.checkpoint("jeeves.session.patch", consume_step=True)
            patch_result = session.apply(
                operations,
                capability="world.patch",
                evidence_ids=evidence_ids,
            )
            execution.record(
                "jeeves.session.patched",
                {
                    "session_id": session.session_id,
                    "before_hash": patch_result.before_hash,
                    "after_hash": patch_result.after_hash,
                    "operations": len(operations),
                },
            )

            execution.checkpoint("jeeves.session.evaluate", consume_step=True)
            evaluation = session.evaluate(
                self.policy,
                baseline_metrics=baseline_metrics,
                candidate_metrics=candidate_metrics,
                evidence_ids=evidence_ids,
                mode=mode,
            )
            execution.record(
                "jeeves.session.evaluated",
                {
                    "session_id": session.session_id,
                    "accepted": evaluation.decision.accepted,
                    "gain": evaluation.decision.gain,
                    "violations": list(evaluation.decision.violations),
                    "mode": mode.value,
                },
                ok=evaluation.decision.accepted,
            )

            if not evaluation.decision.accepted:
                status = "rejected"
                session.discard()
            else:
                should_adopt = auto_adopt and (
                    mode is ChangeMode.EVOLVE or mutation_approved
                )
                if should_adopt:
                    if not self.runtime.governor.permits(execution.priority, mutates=True):
                        status = "write_blocked"
                        self._store_pending(
                            _PendingEvolution(
                                session=session,
                                evaluation=evaluation,
                                mode=mode,
                                agent_id=agent_id,
                                route=route,
                                evidence_ids=evidence_ids,
                                created_at=time.time(),
                            )
                        )
                    else:
                        execution.checkpoint("jeeves.session.adopt", consume_step=True)
                        adoption = session.adopt(
                            canonical,
                            evaluation,
                            capability="world.adopt",
                            evidence_ids=evidence_ids,
                        )
                        status = "adopted"
                        execution.record(
                            "jeeves.session.adopted",
                            {
                                "session_id": session.session_id,
                                "revision": adoption.canonical_patch.to_revision,
                                "semantic_hash": adoption.canonical_patch.after_hash,
                            },
                        )
                else:
                    status = (
                        "approval_required"
                        if mode is ChangeMode.MUTATE and not mutation_approved
                        else "accepted_pending"
                    )
                    self._store_pending(
                        _PendingEvolution(
                            session=session,
                            evaluation=evaluation,
                            mode=mode,
                            agent_id=agent_id,
                            route=route,
                            evidence_ids=evidence_ids,
                            created_at=time.time(),
                        )
                    )

            try:
                memory_ids = self._remember(
                    agent_id=agent_id,
                    run_id=run_id,
                    status=status,
                    evaluation=evaluation,
                    route=route,
                    adopted=adoption is not None,
                )
                execution.record(
                    "jeeves.memory.recorded",
                    {"memory_ids": list(memory_ids)},
                )
            except Exception as exc:  # memory must not invalidate an adopted world
                execution.record(
                    "jeeves.memory.failed",
                    {"error_type": type(exc).__name__, "error": str(exc)[:300]},
                    ok=False,
                )

        # Capture only after the execution context exits so callers receive the
        # final state, including execution.finish and governor bookkeeping.
        execution_snapshot = execution.snapshot()
        evidence = tuple(execution.evidence())
        return WorldEvolutionOutcome(
            run_id=run_id,
            status=status,
            session_id=evaluation.session_id,
            route=route,
            evaluation=evaluation,
            adoption=adoption,
            execution=execution_snapshot,
            evidence=evidence,
            memory_ids=memory_ids,
        )

    def adopt_pending(
        self,
        session_id: str,
        canonical: WorldGraph,
        *,
        approved: bool = False,
        priority: Priority | str | int = Priority.INTERACTIVE,
        max_steps: int | None = 4,
        max_seconds: float | None = 15.0,
        admission_timeout: float | None = 5.0,
    ) -> PendingAdoptionOutcome:
        """Adopt a previously accepted candidate against its original base."""
        pending = self._get_pending(session_id)
        if pending.mode is ChangeMode.MUTATE and not approved:
            raise ApprovalRequired(f"mutation session requires approval: {session_id}")

        run_id = uuid.uuid4().hex[:16]
        memory_ids: tuple[str, ...] = ()
        with self.runtime.execution(
            run_id=run_id,
            build_id=canonical.semantic_hash(),
            priority=priority,
            max_steps=max_steps,
            max_seconds=max_seconds,
            admission_timeout=admission_timeout,
        ) as execution:
            execution.checkpoint("jeeves.pending.adopt", consume_step=True)
            if not self.runtime.governor.permits(execution.priority, mutates=True):
                raise CapabilityRejected("runtime governor blocks canonical world writes")

            adoption = pending.session.adopt(
                canonical,
                pending.evaluation,
                capability="world.adopt.pending",
                evidence_ids=pending.evidence_ids,
            )
            # Remove only after a successful canonical adoption; a conflict leaves the
            # candidate available for inspection/discard rather than silently losing it.
            self._pop_pending(session_id)
            execution.record(
                "jeeves.pending.adopted",
                {
                    "session_id": session_id,
                    "revision": adoption.canonical_patch.to_revision,
                    "semantic_hash": adoption.canonical_patch.after_hash,
                },
            )
            try:
                memory_ids = self._remember(
                    agent_id=pending.agent_id,
                    run_id=run_id,
                    status="adopted_pending",
                    evaluation=pending.evaluation,
                    route=pending.route,
                    adopted=True,
                )
            except Exception as exc:
                execution.record(
                    "jeeves.memory.failed",
                    {"error_type": type(exc).__name__, "error": str(exc)[:300]},
                    ok=False,
                )

        execution_snapshot = execution.snapshot()
        evidence = tuple(execution.evidence())
        return PendingAdoptionOutcome(
            run_id=run_id,
            session_id=session_id,
            adoption=adoption,
            execution=execution_snapshot,
            evidence=evidence,
            memory_ids=memory_ids,
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            "runtime": self.runtime.snapshot(),
            "router": self.router.snapshot(),
            "pending": [row.as_dict() for row in self.pending()],
        }
