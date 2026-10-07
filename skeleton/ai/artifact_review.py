"""Version-bound artifact review state machine for VOL-209."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum


class ReviewError(ValueError):
    pass


class ReviewState(str, Enum):
    OPEN="open"
    CHANGES_REQUESTED="changes_requested"
    APPROVED="approved"
    SUPERSEDED="superseded"


@dataclass(frozen=True)
class ReviewComment:
    reviewer_id: str
    body: str
    evidence_refs: tuple[str,...]=()
    blocking: bool=False

    def __post_init__(self):
        if not self.reviewer_id.strip() or not self.body.strip():
            raise ReviewError("reviewer and comment body are required")
        if self.blocking and not self.evidence_refs:
            raise ReviewError("blocking comment requires evidence")


@dataclass(frozen=True)
class ReviewDecision:
    reviewer_id: str
    artifact_digest: str
    approved: bool
    evidence_refs: tuple[str,...]

    def __post_init__(self):
        if not self.reviewer_id.strip() or not self.artifact_digest.strip() or not self.evidence_refs:
            raise ReviewError("decision identity, artifact digest, and evidence are required")


@dataclass
class ArtifactReview:
    artifact_id: str
    artifact_digest: str
    required_reviewers: frozenset[str]
    required_gates: frozenset[str]
    state: ReviewState=ReviewState.OPEN
    comments: list[ReviewComment]=field(default_factory=list)
    decisions: dict[str,ReviewDecision]=field(default_factory=dict)
    passed_gates: set[str]=field(default_factory=set)

    def __post_init__(self):
        if not self.artifact_id.strip() or not self.artifact_digest.strip():
            raise ReviewError("artifact identity and digest are required")
        if not self.required_reviewers:
            raise ReviewError("at least one reviewer is required")

    def comment(self, item: ReviewComment) -> None:
        self._ensure_active()
        self.comments.append(item)
        if item.blocking:
            self.state=ReviewState.CHANGES_REQUESTED

    def decide(self, decision: ReviewDecision) -> None:
        self._ensure_active()
        if decision.reviewer_id not in self.required_reviewers:
            raise ReviewError("reviewer is not required/authorized")
        if decision.artifact_digest != self.artifact_digest:
            raise ReviewError("stale decision targets a different artifact version")
        self.decisions[decision.reviewer_id]=decision
        self._recompute()

    def pass_gate(self, gate: str, artifact_digest: str) -> None:
        self._ensure_active()
        if gate not in self.required_gates:
            raise ReviewError("undeclared gate cannot satisfy review")
        if artifact_digest != self.artifact_digest:
            raise ReviewError("stale gate evidence targets a different artifact version")
        self.passed_gates.add(gate)
        self._recompute()

    def supersede(self, new_digest: str) -> "ArtifactReview":
        self._ensure_active()
        if not new_digest.strip() or new_digest == self.artifact_digest:
            raise ReviewError("new artifact version must have a distinct digest")
        self.state=ReviewState.SUPERSEDED
        return ArtifactReview(self.artifact_id,new_digest,self.required_reviewers,self.required_gates)

    @property
    def promotable(self) -> bool:
        return self.state is ReviewState.APPROVED

    def _ensure_active(self) -> None:
        if self.state is ReviewState.SUPERSEDED:
            raise ReviewError("superseded review is immutable")

    def _recompute(self) -> None:
        if any(c.blocking for c in self.comments):
            self.state=ReviewState.CHANGES_REQUESTED
            return
        approvals={r for r,d in self.decisions.items() if d.approved}
        rejection=any(not d.approved for d in self.decisions.values())
        if rejection:
            self.state=ReviewState.CHANGES_REQUESTED
        elif approvals == set(self.required_reviewers) and self.passed_gates == set(self.required_gates):
            self.state=ReviewState.APPROVED
        else:
            self.state=ReviewState.OPEN
