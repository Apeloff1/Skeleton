"""Executable VS-002 through VS-007 contracts for P3.

The vertical-suite harness intentionally uses small deterministic fixtures while
preserving the production invariants named in the masterplan.  A fixture can
prove a contract boundary exists and fails closed; it cannot by itself promote
the owning masterplan volume or substitute for independent verification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
from typing import Mapping, Sequence


class VerticalSuiteError(RuntimeError):
    """A vertical-slice contract or acceptance condition is violated."""


def _text(name: str, value: object, maximum: int = 4096) -> str:
    if not isinstance(value, str) or not value.strip():
        raise VerticalSuiteError(f"{name} must be non-empty text")
    result = value.strip()
    if len(result) > maximum:
        raise VerticalSuiteError(f"{name} exceeds {maximum} characters")
    return result


def _unique(name: str, values: Sequence[str], *, minimum: int = 0) -> tuple[str, ...]:
    result: list[str] = []
    for raw in values:
        item = _text(name, raw)
        if item in result:
            raise VerticalSuiteError(f"{name} contains duplicate {item}")
        result.append(item)
    if len(result) < minimum:
        raise VerticalSuiteError(f"{name} requires at least {minimum} entries")
    return tuple(result)


def _digest(value: object) -> str:
    try:
        raw = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise VerticalSuiteError("vertical-suite value is not deterministic JSON") from exc
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _sha(name: str, value: object) -> str:
    result = _text(name, value, 64).lower()
    if len(result) != 64 or any(ch not in "0123456789abcdef" for ch in result):
        raise VerticalSuiteError(f"{name} must be lowercase sha256")
    return result


# VS-002 -------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EngineeringTask:
    task_id: str
    objective: str
    target_paths: tuple[str, ...]
    repository_graph_digest: str
    rollback_ref: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_id", _text("task_id", self.task_id, 256))
        object.__setattr__(self, "objective", _text("objective", self.objective))
        object.__setattr__(
            self, "target_paths", _unique("target_path", self.target_paths, minimum=1)
        )
        object.__setattr__(
            self,
            "repository_graph_digest",
            _sha("repository_graph_digest", self.repository_graph_digest),
        )
        object.__setattr__(self, "rollback_ref", _text("rollback_ref", self.rollback_ref, 512))


@dataclass(frozen=True, slots=True)
class MutationLease:
    lease_id: str
    task_id: str
    owner_id: str
    fencing_token: int
    target_paths: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "lease_id", _text("lease_id", self.lease_id, 256))
        object.__setattr__(self, "task_id", _text("task_id", self.task_id, 256))
        object.__setattr__(self, "owner_id", _text("owner_id", self.owner_id, 256))
        if (
            isinstance(self.fencing_token, bool)
            or not isinstance(self.fencing_token, int)
            or self.fencing_token <= 0
        ):
            raise VerticalSuiteError("fencing_token must be a positive integer")
        object.__setattr__(
            self, "target_paths", _unique("target_path", self.target_paths, minimum=1)
        )


@dataclass(frozen=True, slots=True)
class EngineeringEvidence:
    task_id: str
    lease_id: str
    change_digest: str
    test_refs: tuple[str, ...]
    review_refs: tuple[str, ...]
    verifier_id: str
    rollback_ref: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_id", _text("task_id", self.task_id, 256))
        object.__setattr__(self, "lease_id", _text("lease_id", self.lease_id, 256))
        object.__setattr__(self, "change_digest", _sha("change_digest", self.change_digest))
        object.__setattr__(self, "test_refs", _unique("test_ref", self.test_refs, minimum=1))
        object.__setattr__(self, "review_refs", _unique("review_ref", self.review_refs, minimum=1))
        object.__setattr__(self, "verifier_id", _text("verifier_id", self.verifier_id, 256))
        object.__setattr__(self, "rollback_ref", _text("rollback_ref", self.rollback_ref, 512))


class EngineeringAgentFixture:
    def plan(self, task: EngineeringTask) -> tuple[dict[str, object], ...]:
        if not isinstance(task, EngineeringTask):
            raise TypeError("task must be EngineeringTask")
        return tuple(
            {
                "path": path,
                "objective": task.objective,
                "repository_graph_digest": task.repository_graph_digest,
            }
            for path in task.target_paths
        )

    def verify(
        self,
        *,
        task: EngineeringTask,
        lease: MutationLease,
        change: Mapping[str, object],
        test_refs: Sequence[str],
        review_refs: Sequence[str],
        implementer_id: str,
        verifier_id: str,
    ) -> EngineeringEvidence:
        if lease.task_id != task.task_id:
            raise VerticalSuiteError("mutation lease task mismatch")
        if set(lease.target_paths) != set(task.target_paths):
            raise VerticalSuiteError("mutation lease target scope mismatch")
        if _text("implementer_id", implementer_id, 256) == _text(
            "verifier_id", verifier_id, 256
        ):
            raise VerticalSuiteError("engineering verifier must be independent")
        return EngineeringEvidence(
            task_id=task.task_id,
            lease_id=lease.lease_id,
            change_digest=_digest(dict(change)),
            test_refs=tuple(test_refs),
            review_refs=tuple(review_refs),
            verifier_id=verifier_id,
            rollback_ref=task.rollback_ref,
        )


# VS-003 -------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ResearchQuestion:
    question_id: str
    question: str
    preregistered_metrics: tuple[str, ...]
    source_refs: tuple[str, ...]
    limitation_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "question_id", _text("question_id", self.question_id, 256))
        object.__setattr__(self, "question", _text("question", self.question))
        object.__setattr__(
            self,
            "preregistered_metrics",
            _unique("metric", self.preregistered_metrics, minimum=1),
        )
        object.__setattr__(self, "source_refs", _unique("source_ref", self.source_refs, minimum=1))
        object.__setattr__(
            self, "limitation_refs", _unique("limitation_ref", self.limitation_refs, minimum=1)
        )


@dataclass(frozen=True, slots=True)
class EvidenceGraph:
    question_id: str
    claim_source_edges: tuple[tuple[str, str], ...]
    negative_outcome_refs: tuple[str, ...]
    reproduction_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.claim_source_edges:
            raise VerticalSuiteError("research evidence graph requires claim/source edges")
        if not self.negative_outcome_refs:
            raise VerticalSuiteError("research graph must preserve negative/ambiguous outcomes")
        if not self.reproduction_refs:
            raise VerticalSuiteError("research graph requires reproduction evidence")


@dataclass(frozen=True, slots=True)
class ResearchConclusion:
    question_id: str
    conclusion: str
    evidence_digest: str
    metric_results: Mapping[str, float]
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "question_id", _text("question_id", self.question_id, 256))
        object.__setattr__(self, "conclusion", _text("conclusion", self.conclusion))
        object.__setattr__(self, "evidence_digest", _sha("evidence_digest", self.evidence_digest))
        if not self.limitations:
            raise VerticalSuiteError("research conclusion must preserve limitations")
        object.__setattr__(self, "metric_results", dict(self.metric_results))


class ScientificResearchFixture:
    def conclude(
        self,
        question: ResearchQuestion,
        graph: EvidenceGraph,
        *,
        metric_results: Mapping[str, float],
        conclusion: str,
    ) -> ResearchConclusion:
        if graph.question_id != question.question_id:
            raise VerticalSuiteError("research graph question mismatch")
        if set(metric_results) != set(question.preregistered_metrics):
            raise VerticalSuiteError("research metric set drifted from preregistration")
        return ResearchConclusion(
            question_id=question.question_id,
            conclusion=conclusion,
            evidence_digest=_digest(
                {
                    "edges": list(graph.claim_source_edges),
                    "negative": list(graph.negative_outcome_refs),
                    "reproductions": list(graph.reproduction_refs),
                }
            ),
            metric_results=metric_results,
            limitations=question.limitation_refs,
        )


# VS-004 -------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MultiAgentTask:
    task_id: str
    role_scopes: Mapping[str, tuple[str, ...]]

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_id", _text("task_id", self.task_id, 256))
        if len(self.role_scopes) < 2:
            raise VerticalSuiteError("multi-agent fixture requires at least two roles")
        normalized: dict[str, tuple[str, ...]] = {}
        for role, paths in self.role_scopes.items():
            normalized[_text("role", role, 256)] = _unique("role_scope", paths, minimum=1)
        object.__setattr__(self, "role_scopes", normalized)


@dataclass(frozen=True, slots=True)
class HandoffPacket:
    from_role: str
    to_role: str
    task_id: str
    artifact_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    authority_subset: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.from_role == self.to_role:
            raise VerticalSuiteError("handoff roles must differ")
        object.__setattr__(self, "from_role", _text("from_role", self.from_role, 256))
        object.__setattr__(self, "to_role", _text("to_role", self.to_role, 256))
        object.__setattr__(self, "task_id", _text("task_id", self.task_id, 256))
        object.__setattr__(
            self, "artifact_refs", _unique("artifact_ref", self.artifact_refs, minimum=1)
        )
        object.__setattr__(
            self, "evidence_refs", _unique("evidence_ref", self.evidence_refs, minimum=1)
        )
        object.__setattr__(
            self, "authority_subset", _unique("authority", self.authority_subset, minimum=1)
        )


@dataclass(frozen=True, slots=True)
class ConflictDomain:
    roles: tuple[str, str]
    overlapping_paths: tuple[str, ...]


class MultiAgentEngineeringFixture:
    def conflicts(self, task: MultiAgentTask) -> tuple[ConflictDomain, ...]:
        items = list(task.role_scopes.items())
        conflicts: list[ConflictDomain] = []
        for index, (left_role, left_paths) in enumerate(items):
            for right_role, right_paths in items[index + 1 :]:
                overlap = tuple(sorted(set(left_paths) & set(right_paths)))
                if overlap:
                    conflicts.append(
                        ConflictDomain((left_role, right_role), overlap)
                    )
        return tuple(conflicts)

    def validate_handoff(
        self, task: MultiAgentTask, packet: HandoffPacket
    ) -> None:
        if packet.task_id != task.task_id:
            raise VerticalSuiteError("handoff task mismatch")
        if packet.from_role not in task.role_scopes or packet.to_role not in task.role_scopes:
            raise VerticalSuiteError("handoff references unknown role")
        sender_scope = set(task.role_scopes[packet.from_role])
        if not set(packet.authority_subset) <= sender_scope:
            raise VerticalSuiteError("handoff amplifies sender authority")


# VS-005 -------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ImprovementCandidate:
    candidate_id: str
    champion_digest: str
    challenger_digest: str
    isolated_scope_ref: str
    preregistered_metrics: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_id", _text("candidate_id", self.candidate_id, 256))
        object.__setattr__(self, "champion_digest", _sha("champion_digest", self.champion_digest))
        object.__setattr__(self, "challenger_digest", _sha("challenger_digest", self.challenger_digest))
        object.__setattr__(
            self, "isolated_scope_ref", _text("isolated_scope_ref", self.isolated_scope_ref, 512)
        )
        object.__setattr__(
            self,
            "preregistered_metrics",
            _unique("metric", self.preregistered_metrics, minimum=4),
        )


@dataclass(frozen=True, slots=True)
class PromotionDecision:
    candidate_id: str
    promoted: bool
    verifier_id: str
    evaluation_refs: tuple[str, ...]
    canary_ref: str
    rollback_ref: str


@dataclass(frozen=True, slots=True)
class RollbackReceipt:
    candidate_id: str
    from_digest: str
    to_digest: str
    reason: str


class SelfImprovementFixture:
    REQUIRED_METRICS = frozenset({"quality", "safety", "cost", "robustness"})

    def decide(
        self,
        candidate: ImprovementCandidate,
        *,
        metric_results: Mapping[str, float],
        implementer_id: str,
        verifier_id: str,
        evaluation_refs: Sequence[str],
        canary_ref: str,
        rollback_ref: str,
    ) -> PromotionDecision:
        if not self.REQUIRED_METRICS <= set(candidate.preregistered_metrics):
            raise VerticalSuiteError("self-improvement metric contract is incomplete")
        if set(metric_results) != set(candidate.preregistered_metrics):
            raise VerticalSuiteError("self-improvement metric set drift")
        if implementer_id == verifier_id:
            raise VerticalSuiteError("self-improvement verifier must be independent")
        promoted = all(float(value) >= 0.0 for value in metric_results.values())
        return PromotionDecision(
            candidate_id=candidate.candidate_id,
            promoted=promoted,
            verifier_id=_text("verifier_id", verifier_id, 256),
            evaluation_refs=_unique("evaluation_ref", evaluation_refs, minimum=2),
            canary_ref=_text("canary_ref", canary_ref, 512),
            rollback_ref=_text("rollback_ref", rollback_ref, 512),
        )

    def rollback(
        self,
        candidate: ImprovementCandidate,
        *,
        reason: str,
    ) -> RollbackReceipt:
        return RollbackReceipt(
            candidate_id=candidate.candidate_id,
            from_digest=candidate.challenger_digest,
            to_digest=candidate.champion_digest,
            reason=_text("reason", reason),
        )


# VS-006 -------------------------------------------------------------------


class DistributedOutcome(str, Enum):
    COMMITTED = "committed"
    NOT_COMMITTED = "not_committed"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class DistributedTask:
    task_id: str
    idempotency_key: str
    effect_ref: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_id", _text("task_id", self.task_id, 256))
        object.__setattr__(
            self, "idempotency_key", _text("idempotency_key", self.idempotency_key, 512)
        )
        object.__setattr__(self, "effect_ref", _text("effect_ref", self.effect_ref, 512))


@dataclass(frozen=True, slots=True)
class WorkerLease:
    lease_id: str
    worker_id: str
    fencing_token: int

    def __post_init__(self) -> None:
        if (
            isinstance(self.fencing_token, bool)
            or not isinstance(self.fencing_token, int)
            or self.fencing_token <= 0
        ):
            raise VerticalSuiteError("worker fencing token must be positive")


@dataclass(frozen=True, slots=True)
class DistributedReceipt:
    task_id: str
    idempotency_key: str
    fencing_token: int
    outcome: DistributedOutcome
    reconciliation_refs: tuple[str, ...] = ()


class DistributedExecutionFixture:
    def __init__(self) -> None:
        self._latest_fencing: dict[str, int] = {}
        self._committed_keys: set[str] = set()

    def execute(
        self,
        task: DistributedTask,
        lease: WorkerLease,
        *,
        observed_outcome: DistributedOutcome,
        reconciliation_refs: Sequence[str] = (),
    ) -> DistributedReceipt:
        latest = self._latest_fencing.get(task.task_id, 0)
        if lease.fencing_token <= latest:
            raise VerticalSuiteError("stale worker lease/fencing token")
        self._latest_fencing[task.task_id] = lease.fencing_token
        refs = tuple(reconciliation_refs)
        if observed_outcome is DistributedOutcome.UNKNOWN and not refs:
            raise VerticalSuiteError("unknown distributed outcome requires reconciliation")
        if task.idempotency_key in self._committed_keys and observed_outcome is DistributedOutcome.COMMITTED:
            raise VerticalSuiteError("duplicate external effect blocked by idempotency")
        if observed_outcome is DistributedOutcome.COMMITTED:
            self._committed_keys.add(task.idempotency_key)
        return DistributedReceipt(
            task_id=task.task_id,
            idempotency_key=task.idempotency_key,
            fencing_token=lease.fencing_token,
            outcome=observed_outcome,
            reconciliation_refs=refs,
        )


# VS-007 -------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DesktopArtifactReceipt:
    release_digest: str
    signed_release_ref: str
    governed_operation_ref: str
    artifact_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "release_digest", _sha("release_digest", self.release_digest))
        object.__setattr__(self, "signed_release_ref", _text("signed_release_ref", self.signed_release_ref, 512))
        object.__setattr__(self, "governed_operation_ref", _text("governed_operation_ref", self.governed_operation_ref, 512))
        object.__setattr__(self, "artifact_digest", _sha("artifact_digest", self.artifact_digest))


@dataclass(frozen=True, slots=True)
class DesktopRollbackEvidence:
    before_state_digest: str
    migrated_state_digest: str
    rollback_state_digest: str
    update_interruption_ref: str

    def __post_init__(self) -> None:
        for name in ("before_state_digest", "migrated_state_digest", "rollback_state_digest"):
            object.__setattr__(self, name, _sha(name, getattr(self, name)))
        object.__setattr__(
            self,
            "update_interruption_ref",
            _text("update_interruption_ref", self.update_interruption_ref, 512),
        )


@dataclass(frozen=True, slots=True)
class DesktopAcceptanceRun:
    environment_id: str
    install_ref: str
    artifact: DesktopArtifactReceipt
    restart_ref: str
    update_ref: str
    migration_ref: str
    rollback: DesktopRollbackEvidence

    def __post_init__(self) -> None:
        for name in ("environment_id", "install_ref", "restart_ref", "update_ref", "migration_ref"):
            object.__setattr__(self, name, _text(name, getattr(self, name), 512))

    @property
    def preserves_authoritative_state(self) -> bool:
        return self.rollback.before_state_digest == self.rollback.rollback_state_digest


class DesktopProductFixture:
    def accept(self, run: DesktopAcceptanceRun) -> str:
        if not run.artifact.signed_release_ref.startswith("signature:"):
            raise VerticalSuiteError("desktop release must be signed")
        if not run.artifact.governed_operation_ref.startswith("operation:"):
            raise VerticalSuiteError("desktop acceptance requires governed AI operation")
        if not run.preserves_authoritative_state:
            raise VerticalSuiteError("desktop rollback does not restore authoritative state")
        return _digest(
            {
                "environment": run.environment_id,
                "install": run.install_ref,
                "operation": run.artifact.governed_operation_ref,
                "artifact": run.artifact.artifact_digest,
                "restart": run.restart_ref,
                "update": run.update_ref,
                "migration": run.migration_ref,
                "rollback": run.rollback.rollback_state_digest,
            }
        )


__all__ = [
    "DesktopAcceptanceRun",
    "DesktopArtifactReceipt",
    "DesktopProductFixture",
    "DesktopRollbackEvidence",
    "DistributedExecutionFixture",
    "DistributedOutcome",
    "DistributedReceipt",
    "DistributedTask",
    "EngineeringAgentFixture",
    "EngineeringEvidence",
    "EngineeringTask",
    "EvidenceGraph",
    "HandoffPacket",
    "ImprovementCandidate",
    "MultiAgentEngineeringFixture",
    "MultiAgentTask",
    "MutationLease",
    "PromotionDecision",
    "ResearchConclusion",
    "ResearchQuestion",
    "RollbackReceipt",
    "ScientificResearchFixture",
    "SelfImprovementFixture",
    "VerticalSuiteError",
    "WorkerLease",
]
