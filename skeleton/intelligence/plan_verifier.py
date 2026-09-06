"""Plan verifier — quality gate for build-plan cards.

Now wired to policy_enforcement for dynamic thresholds.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Mapping, Optional, Tuple

from skeleton.intelligence.quality import QualityIssue, QualityReport, QualitySignal
from skeleton.organism.policy_enforcement import threshold_for

if TYPE_CHECKING:
    from skeleton.intelligence.cognition import Cognition, Schism


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


class PlanVerifier:
    """Verifier for plan/build cards returned by the command deck."""

    def __init__(
        self,
        *,
        accept_at: float | None = None,
        root=None,
        cognition: "Cognition | None" = None,
    ) -> None:
        self.accept_at = accept_at if accept_at is not None else threshold_for("plan", root=root, fallback=0.7)
        self.runs = 0
        self.accepted = 0
        self._root = root
        self._cognition = cognition

    def verify(self, plan: Mapping[str, Any], *, vision: str = "") -> PlanVerificationReport:
        self.runs += 1
        issues = []

        completeness = self._completeness(plan, issues)
        coherence = self._coherence(plan, issues)
        grounding = self._grounding(plan, vision, issues)
        actionability = self._actionability(plan, issues)

        if self._cognition is not None:
            coherence = self._cognition_coherence(plan, self._cognition, issues, coherence)

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
        from skeleton.organism.policy_enforcement import gate_check
        policy_gate = gate_check("plan", score, root=self._root)
        return PlanVerificationReport(
            accepted=accepted,
            score=score,
            reason=reason,
            weakest_path=weakest,
            thresholds={"plan_accept_at": self.accept_at},
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

    def _completeness(self, plan: Mapping[str, Any], issues: list[str]) -> float:
        required = ("era", "primary_dps", "room_bias")
        hits = sum(1 for k in required if plan.get(k) not in (None, "", []))
        score = hits / len(required)
        if hits < len(required):
            missing = [k for k in required if plan.get(k) in (None, "", [])]
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

    def ingest_claim(
        self,
        predicate: str,
        polarity: bool,
        witness: str,
        supports: bool,
        weight: float,
    ) -> List["Schism"]:
        """Update cognition with a claim and return open schisms for that predicate."""
        if self._cognition is None:
            raise RuntimeError("PlanVerifier has no cognition engine")
        bid = self._cognition.hold(predicate, polarity)
        self._cognition.testify(bid, witness, supports, weight)
        return [s for s in self._cognition.schisms() if s.predicate == predicate]

    def _cognition_coherence(
        self,
        plan: Mapping[str, Any],
        cognition: "Cognition",
        issues: list[str],
        coherence: float,
    ) -> float:
        """Assert plan claims into cognition; open schisms → hard issue + score penalty."""
        raw = plan.get("claims")
        if raw is None:
            raw = plan.get("beliefs")
        claims: list = list(raw) if isinstance(raw, (list, tuple)) else []
        if not claims:
            return coherence
        opened = cognition.assert_plan_claims(claims)
        # Also surface any open schisms on claimed predicates (pre-seeded opposition).
        claimed = {
            str(c.get("predicate") or "").strip()
            for c in claims
            if isinstance(c, Mapping) and str(c.get("predicate") or "").strip()
        }
        by_pred = {s.predicate: s for s in cognition.schisms() if s.predicate in claimed}
        for s in opened:
            by_pred[s.predicate] = s
        if not by_pred:
            return coherence
        for pred in sorted(by_pred):
            issues.append(f"hard: schism on predicate {pred}")
        penalty = min(0.5, 0.25 * len(by_pred))
        return max(0.0, coherence - penalty)

