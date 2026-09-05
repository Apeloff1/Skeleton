"""NPC verifier — shared quality contract for NPC pipeline outputs.

Now wired to policy_enforcement for dynamic thresholds.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Tuple

from skeleton.intelligence.quality import QualityIssue, QualityReport, QualitySignal
from skeleton.organism.policy_enforcement import threshold_for


@dataclass(frozen=True)
class NpcVerificationReport:
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


class NpcVerifier:
    def __init__(self, *, accept_at: float | None = None, root=None) -> None:
        self.accept_at = accept_at if accept_at is not None else threshold_for("npc", root=root, fallback=0.7)
        self.runs = 0
        self.accepted = 0
        self._root = root

    def verify(self, spec: Mapping[str, Any], *, description: str = "") -> NpcVerificationReport:
        self.runs += 1
        issues = []
        completeness = self._completeness(spec, issues)
        coherence = self._coherence(spec, issues)
        behavior = self._behavior(spec, issues)
        grounding = self._grounding(spec, description, issues)
        score = round(0.25 * completeness + 0.25 * coherence + 0.30 * behavior + 0.20 * grounding, 4)
        accepted = score >= self.accept_at and not any(i.startswith("hard:") for i in issues)
        if accepted:
            self.accepted += 1
        reason = "accepted" if accepted else "low_score"
        weakest = min({"completeness": completeness, "coherence": coherence, "behavior": behavior, "grounding": grounding}.items(), key=lambda kv: kv[1])[0]
        summary = {"issue_count": len(issues), "hard_issues": sum(1 for i in issues if i.startswith("hard:")), "soft_issues": sum(1 for i in issues if i.startswith("soft:"))}
        quality = QualityReport(
            accepted=accepted,
            reason=reason,
            score=score,
            weakest_path=weakest,
            thresholds={"npc_accept_at": self.accept_at},
            summary=summary,
            issues=tuple(QualityIssue(path="npc", message=i.split(":", 1)[1].strip(), severity="hard" if i.startswith("hard:") else "soft") for i in issues),
            signals=(
                QualitySignal(path="completeness", score=completeness),
                QualitySignal(path="coherence", score=coherence),
                QualitySignal(path="behavior", score=behavior),
                QualitySignal(path="grounding", score=grounding),
            ),
            metadata={"kind": "pipeline", "pipeline": "npc", "description": description[:160]},
        )
        from skeleton.organism.policy_enforcement import gate_check
        policy_gate = gate_check("npc", score, root=self._root)
        return NpcVerificationReport(accepted=accepted, score=score, reason=reason, weakest_path=weakest, thresholds={"npc_accept_at": self.accept_at}, summary=summary, issues=tuple(issues), quality=quality, policy_gate=policy_gate)

    def stats(self) -> Dict[str, Any]:
        return {"runs": self.runs, "accepted": self.accepted, "accept_rate": round(self.accepted / max(1, self.runs), 4)}

    def _completeness(self, spec: Mapping[str, Any], issues: list[str]) -> float:
        required = ("persona", "dialogue_tree", "behaviour_graph")
        hits = sum(1 for k in required if spec.get(k))
        if hits < len(required):
            issues.append("soft: npc spec is missing a core subsystem")
        return hits / len(required)

    def _coherence(self, spec: Mapping[str, Any], issues: list[str]) -> float:
        persona = spec.get("persona") or {}
        score = 1.0
        if not spec.get("name"):
            issues.append("hard: npc has no name")
            score -= 0.4
        if not persona.get("archetype") and not spec.get("archetype"):
            issues.append("hard: npc has no archetype")
            score -= 0.3
        if not persona.get("traits"):
            issues.append("soft: npc persona has no traits")
            score -= 0.3
        return max(0.0, score)

    def _behavior(self, spec: Mapping[str, Any], issues: list[str]) -> float:
        dialogue = spec.get("dialogue_tree") or []
        behavior = spec.get("behaviour_graph") or []
        score = 1.0
        if len(dialogue) < 2:
            issues.append("hard: npc dialogue tree is too small")
            score -= 0.5
        if len(behavior) < 2:
            issues.append("soft: npc behavior graph is thin")
            score -= 0.5
        return max(0.0, score)

    def _grounding(self, spec: Mapping[str, Any], description: str, issues: list[str]) -> float:
        if not description.strip():
            return 1.0
        tokens = [t for t in description.lower().replace("_", " ").split() if len(t) >= 4]
        if not tokens:
            return 1.0
        persona = spec.get("persona") or {}
        hay = " ".join([str(spec.get("name") or ""), str(spec.get("archetype") or ""), str(persona.get("motivation") or ""), " ".join(persona.get("traits") or [])]).lower()
        hits = sum(1 for t in tokens if t in hay)
        score = hits / len(tokens)
        if score < 0.2:
            issues.append("soft: npc output weakly reflects the description")
        return score
