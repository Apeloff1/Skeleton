"""Isolated live authoring/simulation sessions for Galaxy Studio.

A LiveSession forks canonical WorldGraph state into a detached overlay. Humans,
procedural systems and Jeeves can apply reversible patches to that overlay,
measure the result, then route the candidate through EvolutionPolicy. Canonical
state changes only when an accepted candidate is adopted and the original base
revision/hash are still current.

The design intentionally separates experimentation from adoption. AI autonomy is
therefore cheap inside a session and conservative at the canonical boundary.
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence

from core.evolution_policy import (
    ChangeMode,
    EvolutionCandidate,
    EvolutionDecision,
    EvolutionPolicy,
)
from core.world_graph import (
    PatchOp,
    PatchResult,
    RevisionConflict,
    WorldGraph,
    WorldPatch,
)


class LiveSessionError(RuntimeError):
    """Base error for invalid live-session transitions."""


class SessionClosed(LiveSessionError):
    """Raised when work is attempted after adoption/discard."""


class AdoptionRejected(LiveSessionError):
    """Raised when a candidate has not cleared the evolution gate."""


class SessionState(str, Enum):
    OPEN = "open"
    ADOPTED = "adopted"
    DISCARDED = "discarded"


@dataclass(frozen=True)
class SessionEvaluation:
    session_id: str
    candidate_hash: str
    decision: EvolutionDecision
    baseline_metrics: Mapping[str, float]
    candidate_metrics: Mapping[str, float]

    def as_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "candidate_hash": self.candidate_hash,
            "decision": self.decision.as_dict(),
            "baseline_metrics": dict(self.baseline_metrics),
            "candidate_metrics": dict(self.candidate_metrics),
        }


@dataclass(frozen=True)
class AdoptionResult:
    session_id: str
    canonical_patch: PatchResult
    evaluation: SessionEvaluation
    adopted_at: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "canonical_patch": self.canonical_patch.as_dict(),
            "evaluation": self.evaluation.as_dict(),
            "adopted_at": self.adopted_at,
        }


@dataclass
class _AppliedPatch:
    patch: WorldPatch
    result: PatchResult


class LiveSession:
    """Detached WorldGraph overlay with explicit evaluate/adopt lifecycle."""

    def __init__(
        self,
        canonical: WorldGraph,
        *,
        session_id: str | None = None,
        author: str = "jeeves",
    ) -> None:
        if not isinstance(canonical, WorldGraph):
            raise TypeError("canonical must be a WorldGraph")
        self.session_id = (session_id or uuid.uuid4().hex).strip()
        if not self.session_id:
            raise ValueError("session_id must be non-empty")
        self.author = (author or "jeeves").strip() or "jeeves"
        snapshot = canonical.snapshot()
        self.base_revision = int(snapshot["revision"])
        self.base_hash = str(snapshot["semantic_hash"])
        self._overlay = WorldGraph.from_snapshot(snapshot)
        self._state = SessionState.OPEN
        self._history: list[_AppliedPatch] = []
        self._evaluations: list[SessionEvaluation] = []
        self._adoption: AdoptionResult | None = None
        self._created_at = time.time()
        self._lock = threading.RLock()

    @property
    def state(self) -> SessionState:
        with self._lock:
            return self._state

    @property
    def working_graph(self) -> WorldGraph:
        """Return a detached copy so callers cannot bypass session accounting."""
        with self._lock:
            return WorldGraph.from_snapshot(self._overlay.snapshot())

    def _require_open(self) -> None:
        if self._state is not SessionState.OPEN:
            raise SessionClosed(
                f"live session {self.session_id} is {self._state.value}"
            )

    def apply(
        self,
        operations: Sequence[PatchOp | Mapping[str, Any]],
        *,
        capability: str = "world.patch",
        evidence_ids: Sequence[str] = (),
    ) -> PatchResult:
        """Apply one atomic candidate patch to the detached overlay."""
        with self._lock:
            self._require_open()
            ops = tuple(
                op if isinstance(op, PatchOp) else PatchOp(**dict(op))
                for op in operations
            )
            patch = WorldPatch(
                base_revision=self._overlay.revision,
                operations=ops,
                author=self.author,
                capability=capability,
                evidence_ids=evidence_ids,
                expected_semantic_hash=self._overlay.semantic_hash(),
            )
            result = self._overlay.apply(patch)
            self._history.append(_AppliedPatch(patch, result))
            return result

    def rollback_last(self) -> PatchResult:
        """Undo the latest active candidate patch inside the overlay."""
        with self._lock:
            self._require_open()
            if not self._history:
                raise LiveSessionError("session has no active patch to rollback")
            applied = self._history.pop()
            return self._overlay.rollback(applied.result)

    def preview(self) -> dict[str, Any]:
        with self._lock:
            current_hash = self._overlay.semantic_hash()
            return {
                "session_id": self.session_id,
                "state": self._state.value,
                "author": self.author,
                "base_revision": self.base_revision,
                "base_hash": self.base_hash,
                "overlay_revision": self._overlay.revision,
                "candidate_hash": current_hash,
                "changed": current_hash != self.base_hash,
                "active_patches": len(self._history),
                "active_operations": sum(
                    len(applied.patch.operations) for applied in self._history
                ),
                "evaluations": len(self._evaluations),
                "created_at": self._created_at,
            }

    def evaluate(
        self,
        policy: EvolutionPolicy,
        *,
        baseline_metrics: Mapping[str, float],
        candidate_metrics: Mapping[str, float],
        evidence_ids: Sequence[str],
        mode: ChangeMode | str = ChangeMode.EVOLVE,
        rollback_ref: str | None = None,
    ) -> SessionEvaluation:
        """Score the current overlay candidate without mutating canonical state."""
        if not isinstance(policy, EvolutionPolicy):
            raise TypeError("policy must be an EvolutionPolicy")
        with self._lock:
            self._require_open()
            candidate_hash = self._overlay.semantic_hash()
            if candidate_hash == self.base_hash:
                raise AdoptionRejected("session has no semantic change to evaluate")
            mode = ChangeMode(mode)
            candidate = EvolutionCandidate(
                candidate_id=candidate_hash,
                baseline_id=self.base_hash,
                metrics=dict(candidate_metrics),
                evidence_ids=evidence_ids,
                mode=mode,
                rollback_ref=(
                    rollback_ref
                    if rollback_ref is not None
                    else (f"world:{self.base_hash}" if mode is ChangeMode.MUTATE else None)
                ),
                scope=("world_graph", self.session_id),
            )
            decision = policy.evaluate(dict(baseline_metrics), candidate)
            evaluation = SessionEvaluation(
                session_id=self.session_id,
                candidate_hash=candidate_hash,
                decision=decision,
                baseline_metrics=dict(baseline_metrics),
                candidate_metrics=dict(candidate_metrics),
            )
            self._evaluations.append(evaluation)
            return evaluation

    def _composed_operations(self) -> tuple[PatchOp, ...]:
        operations: list[PatchOp] = []
        for applied in self._history:
            operations.extend(applied.patch.operations)
        return tuple(operations)

    def adopt(
        self,
        canonical: WorldGraph,
        evaluation: SessionEvaluation,
        *,
        capability: str = "world.adopt",
        evidence_ids: Sequence[str] = (),
    ) -> AdoptionResult:
        """Atomically replay an accepted overlay candidate onto canonical state.

        Adoption fails closed when canonical state drifted after this session was
        forked, when the evaluation belongs to another/cached candidate, or when
        the policy rejected the candidate.
        """
        if not isinstance(canonical, WorldGraph):
            raise TypeError("canonical must be a WorldGraph")
        if not isinstance(evaluation, SessionEvaluation):
            raise TypeError("evaluation must be a SessionEvaluation")
        with self._lock:
            self._require_open()
            if evaluation.session_id != self.session_id:
                raise AdoptionRejected("evaluation belongs to another session")
            if not evaluation.decision.accepted:
                raise AdoptionRejected("evolution policy rejected this candidate")
            current_hash = self._overlay.semantic_hash()
            if evaluation.candidate_hash != current_hash:
                raise AdoptionRejected("overlay changed after evaluation")
            if evaluation.decision.candidate_id != current_hash:
                raise AdoptionRejected("decision candidate identity mismatch")
            if canonical.revision != self.base_revision:
                raise RevisionConflict(
                    f"canonical revision drifted: base={self.base_revision}, "
                    f"current={canonical.revision}"
                )
            if canonical.semantic_hash() != self.base_hash:
                raise RevisionConflict("canonical semantic state drifted")

            operations = self._composed_operations()
            if not operations:
                raise AdoptionRejected("session has no active operations to adopt")
            combined_evidence = tuple(
                dict.fromkeys(
                    [
                        *evaluation.decision.reasons,
                        *[str(x).strip() for x in evidence_ids if str(x).strip()],
                    ]
                )
            )
            canonical_patch = WorldPatch(
                base_revision=self.base_revision,
                operations=operations,
                author=self.author,
                capability=capability,
                evidence_ids=combined_evidence,
                expected_semantic_hash=self.base_hash,
            )
            result = canonical.apply(canonical_patch)
            # Replaying the same operations from the same base must produce the
            # exact semantic candidate previously measured.
            if result.after_hash != current_hash:
                # Revert immediately; canonical must never retain an adoption
                # whose measured candidate identity did not reproduce.
                canonical.rollback(result)
                raise AdoptionRejected(
                    "canonical replay did not reproduce evaluated candidate"
                )
            adoption = AdoptionResult(
                session_id=self.session_id,
                canonical_patch=result,
                evaluation=evaluation,
                adopted_at=time.time(),
            )
            self._adoption = adoption
            self._state = SessionState.ADOPTED
            return adoption

    def discard(self) -> dict[str, Any]:
        with self._lock:
            self._require_open()
            self._state = SessionState.DISCARDED
            return self.preview()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                **self.preview(),
                "history": [
                    {
                        "patch": applied.patch.as_dict(),
                        "result": applied.result.as_dict(),
                    }
                    for applied in self._history
                ],
                "evaluation_history": [row.as_dict() for row in self._evaluations],
                "adoption": self._adoption.as_dict() if self._adoption else None,
                "overlay": self._overlay.snapshot(),
            }
