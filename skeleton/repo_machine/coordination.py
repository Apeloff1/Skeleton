"""Repository-scale coordination decisions over planning, topology, and execution frontier."""
from __future__ import annotations

from dataclasses import dataclass

from .model import RepositoryModel
from .workgraph import WorkGraph, WorkNode, build_work_graph


@dataclass(frozen=True, slots=True)
class CoordinationDecision:
    work_identity: str
    action: str
    strategic_score: int
    unlock_potential: int
    confidence: int
    blocked: bool
    reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "work_identity": self.work_identity,
            "action": self.action,
            "strategic_score": self.strategic_score,
            "unlock_potential": self.unlock_potential,
            "confidence": self.confidence,
            "blocked": self.blocked,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True, slots=True)
class CoordinationPlan:
    repository_fingerprint: str
    decisions: tuple[CoordinationDecision, ...]
    bottleneck: str | None
    frontier_size: int

    def as_dict(self) -> dict[str, object]:
        return {
            "repository_fingerprint": self.repository_fingerprint,
            "decisions": [item.as_dict() for item in self.decisions],
            "bottleneck": self.bottleneck,
            "frontier_size": self.frontier_size,
        }


def _confidence(node: WorkNode) -> int:
    confidence = node.topology_confidence
    if node.verification_paths:
        confidence += 10
    if node.readiness == "gated":
        confidence -= 10
    return min(100, max(0, confidence))


def _decision(node: WorkNode) -> CoordinationDecision:
    confidence = _confidence(node)
    reasons = [
        f"strategic score={node.strategic_score}",
        f"unlock potential={node.unlock_potential}",
    ]
    if node.critical_path_depth:
        reasons.append(f"critical-path depth={node.critical_path_depth}")
    if node.blast_radius:
        reasons.append(f"blast radius={node.blast_radius}")
    if confidence < 40:
        reasons.append("low topology confidence requires conservative verification")
    elif confidence >= 80:
        reasons.append("strong topology confidence supports direct execution")
    action = "execute-and-verify" if confidence >= 40 else "inspect-then-verify"
    return CoordinationDecision(
        work_identity=node.identity,
        action=action,
        strategic_score=node.strategic_score,
        unlock_potential=node.unlock_potential,
        confidence=confidence,
        blocked=node.readiness == "gated",
        reasons=tuple(reasons),
    )


def select_next_work(
    model: RepositoryModel,
    *,
    completed: tuple[str, ...] = (),
    active_conflicts: tuple[str, ...] = (),
    limit: int = 8,
) -> CoordinationPlan:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 64:
        raise ValueError("limit must be in [1,64]")
    graph = build_work_graph(model, limit=max(limit, 32))
    frontier = graph.ready(completed, active_conflicts, limit=limit)
    decisions = tuple(_decision(node) for node in frontier)
    critical = graph.critical_path()
    bottleneck = critical[0].identity if critical else None
    return CoordinationPlan(model.fingerprint, decisions, bottleneck, len(graph.frontier(completed)))


def build_coordination_plan(model: RepositoryModel, *, limit: int = 8) -> dict[str, object]:
    return select_next_work(model, limit=limit).as_dict()


__all__ = ["CoordinationDecision", "CoordinationPlan", "build_coordination_plan", "select_next_work"]
