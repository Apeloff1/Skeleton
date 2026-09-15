"""Pipeline verifier — shared quality contract for pipeline outputs.

Now wired to policy_enforcement for dynamic thresholds.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Tuple

from skeleton.intelligence.quality import QualityIssue, QualityReport, QualitySignal


@dataclass(frozen=True)
class PipelineVerificationReport:
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


class PipelineVerifier:
    """Verifier for pipeline outputs, starting with game logic specs."""

    def __init__(self, *, accept_at: float | None = None, root=None) -> None:
        if accept_at is not None:
            self.accept_at = accept_at
        else:
            from skeleton.organism.policy_enforcement import threshold_for
            self.accept_at = threshold_for("game_logic", root=root, fallback=0.7)
        self.runs = 0
        self.accepted = 0
        self._root = root

    def verify_game_logic(self, spec: Mapping[str, Any], *, description: str = "") -> PipelineVerificationReport:
        self.runs += 1
        issues = []

        completeness = self._completeness(spec, issues)
        coherence = self._coherence(spec, issues)
        balance = self._balance(spec, issues)
        grounding = self._grounding(spec, description, issues)

        score = round(
            0.25 * completeness +
            0.25 * coherence +
            0.30 * balance +
            0.20 * grounding,
            4,
        )
        accepted = score >= self.accept_at and not any(i.startswith("hard:") for i in issues)
        if accepted:
            self.accepted += 1
        reason = "accepted" if accepted else "low_score"
        weakest = min(
            {
                "completeness": completeness,
                "coherence": coherence,
                "balance": balance,
                "grounding": grounding,
            }.items(),
            key=lambda kv: kv[1],
        )[0]
        summary = {
            "issue_count": len(issues),
            "hard_issues": sum(1 for i in issues if i.startswith("hard:")),
            "soft_issues": sum(1 for i in issues if i.startswith("soft:")),
        }
        quality = QualityReport(
            accepted=accepted,
            reason=reason,
            score=score,
            weakest_path=weakest,
            thresholds={"pipeline_accept_at": self.accept_at},
            summary=summary,
            issues=tuple(
                QualityIssue(path="game_logic", message=i.split(":", 1)[1].strip(), severity="hard" if i.startswith("hard:") else "soft")
                for i in issues
            ),
            signals=(
                QualitySignal(path="completeness", score=completeness),
                QualitySignal(path="coherence", score=coherence),
                QualitySignal(path="balance", score=balance),
                QualitySignal(path="grounding", score=grounding),
            ),
            metadata={"kind": "pipeline", "pipeline": "game_logic", "description": description[:160]},
        )
        from skeleton.organism.policy_enforcement import gate_check
        policy_gate = gate_check("game_logic", score, root=self._root)
        return PipelineVerificationReport(
            accepted=accepted,
            score=score,
            reason=reason,
            weakest_path=weakest,
            thresholds={"pipeline_accept_at": self.accept_at},
            summary=summary,
            issues=tuple(issues),
            quality=quality,
            policy_gate=policy_gate,
        )

    def stats(self) -> Dict[str, Any]:
        return {
            "runs": self.runs,
            "accepted": self.accepted,
            "accept_rate": round(self.accepted / max(1, self.runs), 4),
        }

    def _completeness(self, spec: Mapping[str, Any], issues: list[str]) -> float:
        required = ("combat", "economy", "progression")
        hits = sum(1 for k in required if spec.get(k))
        score = hits / len(required)
        if hits < len(required):
            issues.append("soft: game logic spec is missing a core subsystem")
        return score

    def _coherence(self, spec: Mapping[str, Any], issues: list[str]) -> float:
        combat = spec.get("combat") or {}
        economy = spec.get("economy") or {}
        progression = spec.get("progression") or {}
        score = 1.0
        if not combat.get("damage_formula"):
            issues.append("hard: combat has no damage formula")
            score -= 0.4
        if not economy.get("currency"):
            issues.append("soft: economy has no named currency")
            score -= 0.2
        if not progression.get("curve"):
            issues.append("hard: progression has no curve")
            score -= 0.4
        return max(0.0, score)

    def _balance(self, spec: Mapping[str, Any], issues: list[str]) -> float:
        combat = spec.get("combat") or {}
        economy = spec.get("economy") or {}
        progression = spec.get("progression") or {}
        score = 1.0
        base_values = combat.get("base_values") or {}
        if any(float(v) < 0 for v in base_values.values()):
            issues.append("hard: combat has negative base stats")
            score -= 0.4
        if float(economy.get("starting_balance") or 0) < 0:
            issues.append("hard: economy starts negative")
            score -= 0.3
        if int(progression.get("max_level") or 0) < 1:
            issues.append("hard: progression max_level is invalid")
            score -= 0.3
        return max(0.0, score)

    def _grounding(self, spec: Mapping[str, Any], description: str, issues: list[str]) -> float:
        if not description.strip():
            return 1.0
        tokens = [t for t in description.lower().replace("_", " ").split() if len(t) >= 4]
        if not tokens:
            return 1.0
        hay = " ".join([
            str(spec.get("title") or ""),
            str((spec.get("economy") or {}).get("currency") or ""),
            str((spec.get("progression") or {}).get("curve") or ""),
            str((spec.get("combat") or {}).get("damage_formula") or ""),
        ]).lower()
        hits = sum(1 for t in tokens if t in hay)
        score = hits / len(tokens)
        if score < 0.2:
            issues.append("soft: pipeline output weakly reflects the description")
        return score
