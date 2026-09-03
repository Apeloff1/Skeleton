"""Plan verifier — quality gate for build-plan cards.

Scores a plan on completeness, coherence, grounding, and actionability,
then emits the shared quality contract so plan and forge speak the same
quality language.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Tuple

from skeleton.intelligence.quality import QualityIssue, QualityReport, QualitySignal


@dataclass(frozen=True)
class PlanVerificationReport:
    accepted: bool
    score: float
    reason: str
    weakest_path: str
    thresholds: Dict[str, float]
    summary: Dict[str, int]
    issues: Tuple[str, ...]
    quality: QualityReport

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
        }


class PlanVerifier:
    """Verifier for plan/build cards returned by the command deck."""

    def __init__(self, *, accept_at: float = 0.7) -> None:
        self.accept_at = accept_at
        self.runs = 0
        self.accepted = 0

    def verify(self, plan: Mapping[str, Any], *, vision: str = "") -> PlanVerificationReport:
        self.runs += 1
        issues = []

        completeness = self._completeness(plan, issues)
        coherence = self._coherence(plan, issues)
        grounding = self._grounding(plan, vision, issues)
        actionability = self._actionability(plan, issues)

        score = round(
            0.30 * completeness +
            0.25 * coherence +
            0.20 * grounding +
            0.25 * actionability,
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
                "grounding": grounding,
                "actionability": actionability,
            }.items(),
            key=lambda kv: kv[1],
        )[0]
        summary = {
            "issue_count": len(issues),
            "hard_issues": sum(1 for i in issues if i.startswith("hard:")),
            "soft_issues": sum(1 for i in issues if i.startswith("soft:")),
        }
        quality_issues = tuple(
            QualityIssue(path="plan", message=i.split(":", 1)[1].strip(), severity="hard" if i.startswith("hard:") else "soft")
            for i in issues
        )
        quality = QualityReport(
            accepted=accepted,
            reason=reason,
            score=score,
            weakest_path=weakest,
            thresholds={"plan_accept_at": self.accept_at},
            summary=summary,
            issues=quality_issues,
            signals=(
                QualitySignal(path="completeness", score=completeness),
                QualitySignal(path="coherence", score=coherence),
                QualitySignal(path="grounding", score=grounding),
                QualitySignal(path="actionability", score=actionability),
            ),
            metadata={"kind": "plan", "vision": vision[:160]},
        )
        return PlanVerificationReport(
            accepted=accepted,
            score=score,
            reason=reason,
            weakest_path=weakest,
            thresholds={"plan_accept_at": self.accept_at},
            summary=summary,
            issues=tuple(issues),
            quality=quality,
        )

    def stats(self) -> Dict[str, Any]:
        return {
            "runs": self.runs,
            "accepted": self.accepted,
            "accept_rate": round(self.accepted / max(1, self.runs), 4),
        }

    def _completeness(self, plan: Mapping[str, Any], issues: list[str]) -> float:
        required = ("era", "primary_dps", "room_bias")
        hits = sum(1 for k in required if plan.get(k) not in {None, "", []})
        score = hits / len(required)
        if hits < len(required):
            missing = [k for k in required if plan.get(k) in {None, "", []}]
            issues.append(f"soft: missing required plan fields {missing}")
        return score

    def _coherence(self, plan: Mapping[str, Any], issues: list[str]) -> float:
        era = str(plan.get("era") or "")
        room_bias = str(plan.get("room_bias") or "")
        primary_dps = plan.get("primary_dps")
        score = 1.0
        if not era:
            issues.append("hard: plan has no era")
            score -= 0.5
        if primary_dps in {None, ""}:
            issues.append("soft: plan has no primary_dps")
            score -= 0.25
        if not room_bias:
            issues.append("soft: plan has no room_bias")
            score -= 0.25
        return max(0.0, score)

    def _grounding(self, plan: Mapping[str, Any], vision: str, issues: list[str]) -> float:
        if not vision.strip():
            return 1.0
        tokens = [t for t in vision.lower().replace("_", " ").split() if len(t) >= 4]
        if not tokens:
            return 1.0
        hay = " ".join(str(plan.get(k) or "") for k in ("era", "title", "room_bias", "citation", "url")).lower()
        hits = sum(1 for t in tokens if t in hay)
        score = hits / len(tokens)
        if score < 0.25:
            issues.append("soft: plan weakly reflects the vision")
        return score

    def _actionability(self, plan: Mapping[str, Any], issues: list[str]) -> float:
        useful = 0
        if plan.get("room_bias"):
            useful += 1
        if plan.get("primary_dps") not in {None, ""}:
            useful += 1
        if plan.get("era"):
            useful += 1
        score = useful / 3.0
        if useful < 2:
            issues.append("soft: plan is thin on buildable direction")
        return score
