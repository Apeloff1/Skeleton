"""Dialogue verifier — shared quality contract for dialogue trees.

Now wired to policy_enforcement for dynamic thresholds.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Tuple

from skeleton.intelligence.quality import QualityIssue, QualityReport, QualitySignal
from skeleton.organism.policy_enforcement import threshold_for


@dataclass(frozen=True)
class DialogueVerificationReport:
    accepted: bool
    score: float
    reason: str
    weakest_path: str
    thresholds: Dict[str, float]
    summary: Dict[str, int]
    issues: Tuple[str, ...]
    quality: QualityReport
    policy_gate: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "accepted": self.accepted,
            "score": round(self.score, 4),
            "reason": self.reason,
            "weakest_path": self.weakest_path,
            "thresholds": {k: round(v, 4) for k, v in self.thresholds.items()},
            "summary": dict(self.summary),
            "issues": list(self.issues),
            "quality": self.quality.to_dict(),
            "policy_gate": self.policy_gate,
        }


class DialogueVerifier:
    def __init__(self, *, accept_at: float | None = None, root=None) -> None:
        if accept_at is not None and (
            isinstance(accept_at, bool) or not isinstance(accept_at, (int, float)) or not 0 < float(accept_at) <= 1
        ):
            raise ValueError("accept_at must be in (0, 1]")
        self.accept_at = accept_at if accept_at is not None else threshold_for("dialogue", root=root, fallback=0.7)
        self.runs = 0
        self.accepted = 0
        self._root = root

    def verify(self, tree: Mapping[str, Any], *, description: str = "") -> DialogueVerificationReport:
        self.runs += 1
        issues = []
        completeness = self._completeness(tree, issues)
        reachability = self._reachability(tree, issues)
        branching = self._branching(tree, issues)
        grounding = self._grounding(tree, description, issues)
        score = round(0.25 * completeness + 0.30 * reachability + 0.25 * branching + 0.20 * grounding, 4)
        accepted = score >= self.accept_at and not any(i.startswith("hard:") for i in issues)
        if accepted:
            self.accepted += 1
        reason = "accepted" if accepted else "low_score"
        weakest = min({"completeness": completeness, "reachability": reachability, "branching": branching, "grounding": grounding}.items(), key=lambda kv: kv[1])[0]
        summary = {"issue_count": len(issues), "hard_issues": sum(1 for i in issues if i.startswith("hard:")), "soft_issues": sum(1 for i in issues if i.startswith("soft:"))}
        quality = QualityReport(
            accepted=accepted,
            reason=reason,
            score=score,
            weakest_path=weakest,
            thresholds={"dialogue_accept_at": self.accept_at},
            summary=summary,
            issues=tuple(QualityIssue(path="dialogue", message=i.split(":", 1)[1].strip(), severity="hard" if i.startswith("hard:") else "soft") for i in issues),
            signals=(
                QualitySignal(path="completeness", score=completeness),
                QualitySignal(path="reachability", score=reachability),
                QualitySignal(path="branching", score=branching),
                QualitySignal(path="grounding", score=grounding),
            ),
            metadata={"kind": "pipeline", "pipeline": "dialogue", "description": description[:160]},
        )
        from skeleton.organism.policy_enforcement import gate_check
        policy_gate = gate_check("dialogue", score, root=self._root)
        return DialogueVerificationReport(accepted=accepted, score=score, reason=reason, weakest_path=weakest, thresholds={"dialogue_accept_at": self.accept_at}, summary=summary, issues=tuple(issues), quality=quality, policy_gate=policy_gate)

    def stats(self) -> Dict[str, Any]:
        return {"runs": self.runs, "accepted": self.accepted, "accept_rate": None if self.runs == 0 else round(self.accepted / self.runs, 4)}

    def _completeness(self, tree: Mapping[str, Any], issues: list[str]) -> float:
        entry = tree.get("entry")
        nodes = tree.get("nodes") or {}
        score = 1.0 if entry and nodes else 0.0
        if score == 0.0:
            issues.append("hard: dialogue tree is missing entry or nodes")
        return score

    def _reachability(self, tree: Mapping[str, Any], issues: list[str]) -> float:
        nodes = tree.get("nodes") or {}
        entry = tree.get("entry")
        if not isinstance(nodes, Mapping) or not isinstance(entry, str) or entry not in nodes or not isinstance(nodes.get(entry), Mapping):
            issues.append("hard: dialogue entry is not a node")
            return 0.0
        seen, stack = set(), [entry]
        while stack:
            current = stack.pop()
            if current in seen or current not in nodes:
                continue
            node = nodes[current]
            if not isinstance(node, Mapping):
                issues.append("hard: dialogue node is not an object")
                return 0.0
            seen.add(current)
            edges = node.get("edges") or []
            if not isinstance(edges, list):
                issues.append("hard: dialogue edges are not a list")
                return 0.0
            for edge in edges:
                if not isinstance(edge, Mapping):
                    issues.append("hard: dialogue edge is not an object")
                    return 0.0
                target = edge.get("target")
                if not isinstance(target, str) or target not in nodes:
                    issues.append("hard: dialogue edge points nowhere")
                    return 0.0
                stack.append(target)
        score = len(seen) / max(1, len(nodes))
        if score < 1.0:
            issues.append("soft: dialogue tree has unreachable nodes")
        return score

    def _branching(self, tree: Mapping[str, Any], issues: list[str]) -> float:
        nodes = tree.get("nodes") or {}
        if not nodes:
            return 0.0
        live = 0
        for node in nodes.values():
            if not isinstance(node, Mapping):
                issues.append("hard: dialogue node is not an object")
                return 0.0
            edges = node.get("edges") or []
            if node.get("terminal") or (isinstance(edges, list) and edges):
                live += 1
            elif edges and not isinstance(edges, list):
                issues.append("hard: dialogue edges are not a list")
                return 0.0
        score = live / len(nodes)
        if score < 1.0:
            issues.append("soft: dialogue tree has dead-air nodes")
        return score

    def _grounding(self, tree: Mapping[str, Any], description: str, issues: list[str]) -> float:
        tokens = [t for t in description.lower().replace("_", " ").split() if len(t) >= 4]
        if not tokens:
            issues.append("hard: dialogue has no description to ground against")
            return 0.0
        nodes = tree.get("nodes") or {}
        hay = " ".join(str((node or {}).get("line") or "") for node in nodes.values()).lower()
        hits = sum(1 for t in tokens if t in hay)
        score = hits / len(tokens)
        if score < 0.2:
            issues.append("soft: dialogue output weakly reflects the description")
        return score
