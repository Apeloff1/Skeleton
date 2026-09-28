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
        if accept_at is not None and (
            isinstance(accept_at, bool) or not isinstance(accept_at, (int, float)) or not 0 < float(accept_at) <= 1
        ):
            raise ValueError("accept_at must be in (0, 1]")
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
            "accept_rate": None if self.runs == 0 else round(self.accepted / self.runs, 4),
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
        tokens = [t for t in vision.lower().replace("_", " ").split() if len(t) >= 4]
        if not tokens:
            issues.append("hard: plan has no vision to ground against")
            return 0.0
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
        """Assert plan claims into cognition; open schisms → hard issue + score penalty.

        Relies on ``Cognition.assert_plan_claims``: a lone plan witness will not
        open a schism by itself; hard failures need pre-seeded opposition or
        ``ingest_claim`` with additional witnesses.
        """
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

# ---------------------------------------------------------------------------
# P1-INTEL-05 deterministic plan analysis and simulation authority.
# ---------------------------------------------------------------------------

from enum import Enum
import hashlib
import json
import math
import re
from typing import Iterable

from skeleton.contracts.canonical import EvidenceRef
from skeleton.contracts.risk_evidence import RiskBindingEvaluation
from skeleton.intelligence.strategy_registry import (
    ReasoningPolicy,
    ReasoningRisk,
    StopDisposition,
    StoppingDecision,
)


PLAN_VERIFIER_SCHEMA_VERSION = 1
PLAN_VERIFIER_TASK_ID = "P1-INTEL-05"
PLAN_VERIFIER_ACCOUNTABILITY_ID = "ACC-P1-INTEL-05"
_PLAN_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,191}$")
_PLAN_MAX_STEPS = 512


class PlanStaticVerifierError(ValueError):
    """Static-plan authority input is malformed."""


class SimulationDisposition(str, Enum):
    COMPLETE = "complete"
    RECOVERED_FAILURE = "recovered_failure"
    UNSAFE_FAILURE = "unsafe_failure"
    BLOCKED = "blocked"


def _plan_token(value: object, field: str) -> str:
    if not isinstance(value, str) or not _PLAN_TOKEN_RE.fullmatch(value):
        raise PlanStaticVerifierError(f"{field} must be a canonical token")
    return value


def _plan_sha256(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise PlanStaticVerifierError(f"{field} must be lowercase sha256")
    return value


def _plan_positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise PlanStaticVerifierError(f"{field} must be a positive integer")
    return value


def _plan_finite(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PlanStaticVerifierError(f"{field} must be finite numeric")
    result = float(value)
    if not math.isfinite(result):
        raise PlanStaticVerifierError(f"{field} must be finite numeric")
    return result


def _plan_positive(value: object, field: str) -> float:
    result = _plan_finite(value, field)
    if result <= 0.0:
        raise PlanStaticVerifierError(f"{field} must be positive")
    return result


def _plan_digest(value: object) -> str:
    try:
        raw = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise PlanStaticVerifierError(
            "plan payload must be canonical JSON"
        ) from exc
    return hashlib.sha256(raw).hexdigest()


def _plan_tokens(
    values: Iterable[str],
    field: str,
    *,
    allow_empty: bool = True,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise PlanStaticVerifierError(
            f"{field} must be an iterable of tokens"
        )
    normalized = tuple(sorted({_plan_token(item, field) for item in values}))
    if not allow_empty and not normalized:
        raise PlanStaticVerifierError(f"{field} must be non-empty")
    return normalized


def _plan_token_sequence(
    values: Iterable[str],
    field: str,
    *,
    allow_empty: bool = True,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise PlanStaticVerifierError(
            f"{field} must be an iterable of tokens"
        )
    result = tuple(_plan_token(item, field) for item in values)
    if not allow_empty and not result:
        raise PlanStaticVerifierError(f"{field} must be non-empty")
    if len(set(result)) != len(result):
        raise PlanStaticVerifierError(f"{field} must not contain duplicates")
    return result


@dataclass(frozen=True, slots=True)
class PlanStep:
    step_id: str
    depends_on: tuple[str, ...] = ()
    preconditions: tuple[str, ...] = ()
    postconditions: tuple[str, ...] = ()
    required_capabilities: tuple[str, ...] = ()
    max_tokens: int = 1
    max_cost_units: float = 0.001
    max_wall_time_s: float = 0.001
    terminal: bool = False
    side_effect: bool = False
    irreversible: bool = False
    recovery_plan_digest: str | None = None
    rollback_test_digest: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "step_id", _plan_token(self.step_id, "step_id")
        )
        object.__setattr__(
            self,
            "depends_on",
            _plan_tokens(self.depends_on, "depends_on"),
        )
        object.__setattr__(
            self,
            "preconditions",
            _plan_tokens(self.preconditions, "preconditions"),
        )
        object.__setattr__(
            self,
            "postconditions",
            _plan_tokens(self.postconditions, "postconditions"),
        )
        object.__setattr__(
            self,
            "required_capabilities",
            _plan_tokens(
                self.required_capabilities,
                "required_capabilities",
            ),
        )
        if self.step_id in self.depends_on:
            raise PlanStaticVerifierError("step cannot depend on itself")
        object.__setattr__(
            self,
            "max_tokens",
            _plan_positive_int(self.max_tokens, "max_tokens"),
        )
        object.__setattr__(
            self,
            "max_cost_units",
            _plan_positive(self.max_cost_units, "max_cost_units"),
        )
        object.__setattr__(
            self,
            "max_wall_time_s",
            _plan_positive(self.max_wall_time_s, "max_wall_time_s"),
        )
        for field in ("terminal", "side_effect", "irreversible"):
            if not isinstance(getattr(self, field), bool):
                raise PlanStaticVerifierError(f"{field} must be boolean")
        if self.irreversible and not self.side_effect:
            raise PlanStaticVerifierError(
                "irreversible step must be a side effect"
            )
        for field in ("recovery_plan_digest", "rollback_test_digest"):
            value = getattr(self, field)
            if value is not None:
                object.__setattr__(
                    self,
                    field,
                    _plan_sha256(value, field),
                )
        if self.side_effect and not self.irreversible:
            if self.recovery_plan_digest is None:
                raise PlanStaticVerifierError(
                    "reversible side effect requires recovery_plan_digest"
                )
            if self.rollback_test_digest is None:
                raise PlanStaticVerifierError(
                    "reversible side effect requires rollback_test_digest"
                )

    def payload(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "depends_on": list(self.depends_on),
            "preconditions": list(self.preconditions),
            "postconditions": list(self.postconditions),
            "required_capabilities": list(self.required_capabilities),
            "max_tokens": self.max_tokens,
            "max_cost_units": self.max_cost_units,
            "max_wall_time_s": self.max_wall_time_s,
            "terminal": self.terminal,
            "side_effect": self.side_effect,
            "irreversible": self.irreversible,
            "recovery_plan_digest": self.recovery_plan_digest,
            "rollback_test_digest": self.rollback_test_digest,
        }

    @property
    def digest(self) -> str:
        return _plan_digest(self.payload())


@dataclass(frozen=True, slots=True)
class StaticPlanDefinition:
    plan_id: str
    version: int
    steps: tuple[PlanStep, ...]
    initial_facts: tuple[str, ...]
    reasoning_policy_digest: str
    planning_history_digest: str
    risk: ReasoningRisk = ReasoningRisk.MEDIUM

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "plan_id", _plan_token(self.plan_id, "plan_id")
        )
        object.__setattr__(
            self, "version", _plan_positive_int(self.version, "version")
        )
        if (
            not isinstance(self.steps, tuple)
            or not self.steps
            or len(self.steps) > _PLAN_MAX_STEPS
        ):
            raise PlanStaticVerifierError(
                "steps must be a bounded non-empty tuple"
            )
        ids: set[str] = set()
        for step in self.steps:
            if not isinstance(step, PlanStep):
                raise PlanStaticVerifierError(
                    "steps must contain PlanStep"
                )
            if step.step_id in ids:
                raise PlanStaticVerifierError(
                    f"duplicate step_id: {step.step_id}"
                )
            ids.add(step.step_id)
        object.__setattr__(
            self,
            "initial_facts",
            _plan_tokens(self.initial_facts, "initial_facts"),
        )
        for field in (
            "reasoning_policy_digest",
            "planning_history_digest",
        ):
            object.__setattr__(
                self,
                field,
                _plan_sha256(getattr(self, field), field),
            )
        try:
            object.__setattr__(self, "risk", ReasoningRisk(self.risk))
        except ValueError as exc:
            raise PlanStaticVerifierError("invalid plan risk") from exc

    def payload(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "version": self.version,
            "steps": [
                step.payload()
                for step in sorted(
                    self.steps,
                    key=lambda item: item.step_id,
                )
            ],
            "initial_facts": list(self.initial_facts),
            "reasoning_policy_digest": self.reasoning_policy_digest,
            "planning_history_digest": self.planning_history_digest,
            "risk": self.risk.value,
        }

    @property
    def digest(self) -> str:
        return _plan_digest(self.payload())


@dataclass(frozen=True, slots=True)
class PlanVerificationPolicy:
    policy_id: str
    version: int
    allowed_capabilities: tuple[str, ...]
    max_steps: int
    max_total_tokens: int
    max_total_cost_units: float
    max_total_wall_time_s: float
    require_terminal_leaves: bool = True
    allow_irreversible: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "policy_id",
            _plan_token(self.policy_id, "policy_id"),
        )
        object.__setattr__(
            self,
            "version",
            _plan_positive_int(self.version, "version"),
        )
        object.__setattr__(
            self,
            "allowed_capabilities",
            _plan_tokens(
                self.allowed_capabilities,
                "allowed_capabilities",
                allow_empty=False,
            ),
        )
        object.__setattr__(
            self,
            "max_steps",
            _plan_positive_int(self.max_steps, "max_steps"),
        )
        if self.max_steps > _PLAN_MAX_STEPS:
            raise PlanStaticVerifierError(
                "max_steps exceeds verifier bound"
            )
        object.__setattr__(
            self,
            "max_total_tokens",
            _plan_positive_int(
                self.max_total_tokens,
                "max_total_tokens",
            ),
        )
        object.__setattr__(
            self,
            "max_total_cost_units",
            _plan_positive(
                self.max_total_cost_units,
                "max_total_cost_units",
            ),
        )
        object.__setattr__(
            self,
            "max_total_wall_time_s",
            _plan_positive(
                self.max_total_wall_time_s,
                "max_total_wall_time_s",
            ),
        )
        for field in (
            "require_terminal_leaves",
            "allow_irreversible",
        ):
            if not isinstance(getattr(self, field), bool):
                raise PlanStaticVerifierError(
                    f"{field} must be boolean"
                )

    def payload(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "version": self.version,
            "allowed_capabilities": list(self.allowed_capabilities),
            "max_steps": self.max_steps,
            "max_total_tokens": self.max_total_tokens,
            "max_total_cost_units": self.max_total_cost_units,
            "max_total_wall_time_s": self.max_total_wall_time_s,
            "require_terminal_leaves": self.require_terminal_leaves,
            "allow_irreversible": self.allow_irreversible,
        }

    @property
    def digest(self) -> str:
        return _plan_digest(self.payload())


@dataclass(frozen=True, slots=True)
class PlanAnalysisDecision:
    accepted: bool
    reasons: tuple[str, ...]
    plan_digest: str
    policy_digest: str
    topological_order: tuple[str, ...]
    root_step_ids: tuple[str, ...]
    leaf_step_ids: tuple[str, ...]
    terminal_step_ids: tuple[str, ...]
    total_tokens: int
    total_cost_units: float
    total_wall_time_s: float
    produced_facts: tuple[str, ...]
    required_capabilities: tuple[str, ...]
    task_id: str = PLAN_VERIFIER_TASK_ID
    accountability_id: str = PLAN_VERIFIER_ACCOUNTABILITY_ID
    schema_version: int = PLAN_VERIFIER_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.accepted, bool):
            raise PlanStaticVerifierError("accepted must be boolean")
        if not isinstance(self.reasons, tuple) or any(
            not isinstance(item, str) or not item
            for item in self.reasons
        ):
            raise PlanStaticVerifierError(
                "reasons must contain non-empty strings"
            )
        for field in ("plan_digest", "policy_digest"):
            object.__setattr__(
                self,
                field,
                _plan_sha256(getattr(self, field), field),
            )
        object.__setattr__(
            self,
            "topological_order",
            _plan_token_sequence(
                self.topological_order,
                "topological_order",
            ),
        )
        for field in (
            "root_step_ids",
            "leaf_step_ids",
            "terminal_step_ids",
            "produced_facts",
            "required_capabilities",
        ):
            object.__setattr__(
                self,
                field,
                _plan_tokens(getattr(self, field), field),
            )
        object.__setattr__(
            self,
            "total_tokens",
            _plan_positive_int(self.total_tokens, "total_tokens"),
        )
        object.__setattr__(
            self,
            "total_cost_units",
            _plan_positive(
                self.total_cost_units,
                "total_cost_units",
            ),
        )
        object.__setattr__(
            self,
            "total_wall_time_s",
            _plan_positive(
                self.total_wall_time_s,
                "total_wall_time_s",
            ),
        )
        if self.task_id != PLAN_VERIFIER_TASK_ID:
            raise PlanStaticVerifierError("task_id drift")
        if self.accountability_id != PLAN_VERIFIER_ACCOUNTABILITY_ID:
            raise PlanStaticVerifierError("accountability_id drift")
        if self.schema_version != PLAN_VERIFIER_SCHEMA_VERSION:
            raise PlanStaticVerifierError("unsupported schema version")

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "accepted": self.accepted,
            "reasons": list(self.reasons),
            "plan_digest": self.plan_digest,
            "policy_digest": self.policy_digest,
            "topological_order": list(self.topological_order),
            "root_step_ids": list(self.root_step_ids),
            "leaf_step_ids": list(self.leaf_step_ids),
            "terminal_step_ids": list(self.terminal_step_ids),
            "total_tokens": self.total_tokens,
            "total_cost_units": self.total_cost_units,
            "total_wall_time_s": self.total_wall_time_s,
            "produced_facts": list(self.produced_facts),
            "required_capabilities": list(
                self.required_capabilities
            ),
        }

    @property
    def decision_digest(self) -> str:
        return _plan_digest(self.payload())


@dataclass(frozen=True, slots=True)
class PlanSimulationDecision:
    accepted: bool
    disposition: SimulationDisposition
    reasons: tuple[str, ...]
    plan_digest: str
    analysis_digest: str
    executed_step_ids: tuple[str, ...]
    final_facts: tuple[str, ...]
    injected_failure_step_id: str | None
    recovered: bool
    task_id: str = PLAN_VERIFIER_TASK_ID
    accountability_id: str = PLAN_VERIFIER_ACCOUNTABILITY_ID
    schema_version: int = PLAN_VERIFIER_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.accepted, bool):
            raise PlanStaticVerifierError("accepted must be boolean")
        try:
            object.__setattr__(
                self,
                "disposition",
                SimulationDisposition(self.disposition),
            )
        except ValueError as exc:
            raise PlanStaticVerifierError(
                "invalid simulation disposition"
            ) from exc
        if not isinstance(self.reasons, tuple) or any(
            not isinstance(item, str) or not item
            for item in self.reasons
        ):
            raise PlanStaticVerifierError(
                "reasons must contain non-empty strings"
            )
        for field in ("plan_digest", "analysis_digest"):
            object.__setattr__(
                self,
                field,
                _plan_sha256(getattr(self, field), field),
            )
        object.__setattr__(
            self,
            "executed_step_ids",
            _plan_token_sequence(
                self.executed_step_ids,
                "executed_step_ids",
            ),
        )
        object.__setattr__(
            self,
            "final_facts",
            _plan_tokens(self.final_facts, "final_facts"),
        )
        if self.injected_failure_step_id is not None:
            object.__setattr__(
                self,
                "injected_failure_step_id",
                _plan_token(
                    self.injected_failure_step_id,
                    "injected_failure_step_id",
                ),
            )
        if not isinstance(self.recovered, bool):
            raise PlanStaticVerifierError(
                "recovered must be boolean"
            )
        if self.task_id != PLAN_VERIFIER_TASK_ID:
            raise PlanStaticVerifierError("task_id drift")
        if self.accountability_id != PLAN_VERIFIER_ACCOUNTABILITY_ID:
            raise PlanStaticVerifierError("accountability_id drift")
        if self.schema_version != PLAN_VERIFIER_SCHEMA_VERSION:
            raise PlanStaticVerifierError("unsupported schema version")

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "accepted": self.accepted,
            "disposition": self.disposition.value,
            "reasons": list(self.reasons),
            "plan_digest": self.plan_digest,
            "analysis_digest": self.analysis_digest,
            "executed_step_ids": list(self.executed_step_ids),
            "final_facts": list(self.final_facts),
            "injected_failure_step_id": self.injected_failure_step_id,
            "recovered": self.recovered,
        }

    @property
    def decision_digest(self) -> str:
        return _plan_digest(self.payload())


@dataclass(frozen=True, slots=True)
class PlanQualificationDecision:
    accepted: bool
    reasons: tuple[str, ...]
    plan_digest: str
    verification_policy_digest: str
    reasoning_policy_digest: str
    analysis_digest: str
    simulation_digest: str
    stopping_digest: str
    risk_evaluation_digest: str | None
    task_id: str = PLAN_VERIFIER_TASK_ID
    accountability_id: str = PLAN_VERIFIER_ACCOUNTABILITY_ID
    schema_version: int = PLAN_VERIFIER_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.accepted, bool):
            raise PlanStaticVerifierError("accepted must be boolean")
        if not isinstance(self.reasons, tuple) or any(
            not isinstance(item, str) or not item
            for item in self.reasons
        ):
            raise PlanStaticVerifierError(
                "reasons must contain non-empty strings"
            )
        for field in (
            "plan_digest",
            "verification_policy_digest",
            "reasoning_policy_digest",
            "analysis_digest",
            "simulation_digest",
            "stopping_digest",
        ):
            object.__setattr__(
                self,
                field,
                _plan_sha256(getattr(self, field), field),
            )
        if self.risk_evaluation_digest is not None:
            object.__setattr__(
                self,
                "risk_evaluation_digest",
                _plan_sha256(
                    self.risk_evaluation_digest,
                    "risk_evaluation_digest",
                ),
            )
        if self.task_id != PLAN_VERIFIER_TASK_ID:
            raise PlanStaticVerifierError("task_id drift")
        if self.accountability_id != PLAN_VERIFIER_ACCOUNTABILITY_ID:
            raise PlanStaticVerifierError("accountability_id drift")
        if self.schema_version != PLAN_VERIFIER_SCHEMA_VERSION:
            raise PlanStaticVerifierError("unsupported schema version")

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "accepted": self.accepted,
            "reasons": list(self.reasons),
            "plan_digest": self.plan_digest,
            "verification_policy_digest": (
                self.verification_policy_digest
            ),
            "reasoning_policy_digest": self.reasoning_policy_digest,
            "analysis_digest": self.analysis_digest,
            "simulation_digest": self.simulation_digest,
            "stopping_digest": self.stopping_digest,
            "risk_evaluation_digest": self.risk_evaluation_digest,
        }

    @property
    def decision_digest(self) -> str:
        return _plan_digest(self.payload())

    def accepted_evidence_ref(
        self,
        *,
        source: str = "p1:intel-05:plan-verifier",
    ) -> EvidenceRef:
        if not self.accepted:
            raise PlanStaticVerifierError(
                "rejected plan qualification cannot become promotion evidence"
            )
        return EvidenceRef(
            source=_plan_token(source, "source"),
            digest=self.decision_digest,
            category="plan_verification",
        )


def _plan_topological_order(
    steps: dict[str, PlanStep],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    indegree = {step_id: 0 for step_id in steps}
    dependents: dict[str, set[str]] = {
        step_id: set() for step_id in steps
    }
    missing: set[str] = set()
    for step in steps.values():
        for dependency in step.depends_on:
            if dependency not in steps:
                missing.add(f"{step.step_id}:{dependency}")
                continue
            indegree[step.step_id] += 1
            dependents[dependency].add(step.step_id)

    ready = sorted(
        step_id
        for step_id, degree in indegree.items()
        if degree == 0
    )
    order: list[str] = []
    while ready:
        current = ready.pop(0)
        order.append(current)
        for child in sorted(dependents[current]):
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
                ready.sort()

    if missing:
        return tuple(order), tuple(
            f"missing-dependency:{item}"
            for item in sorted(missing)
        )
    if len(order) != len(steps):
        cycle_nodes = sorted(
            step_id
            for step_id, degree in indegree.items()
            if degree > 0
        )
        return tuple(order), (
            "cycle-detected:" + ",".join(cycle_nodes),
        )
    return tuple(order), ()


def analyze_static_plan(
    plan: StaticPlanDefinition,
    policy: PlanVerificationPolicy,
) -> PlanAnalysisDecision:
    if not isinstance(plan, StaticPlanDefinition):
        raise TypeError("plan must be StaticPlanDefinition")
    if not isinstance(policy, PlanVerificationPolicy):
        raise TypeError(
            "policy must be PlanVerificationPolicy"
        )

    steps = {step.step_id: step for step in plan.steps}
    order, graph_reasons = _plan_topological_order(steps)
    reasons: list[str] = list(graph_reasons)

    dependents: dict[str, set[str]] = {
        step_id: set() for step_id in steps
    }
    for step in steps.values():
        for dependency in step.depends_on:
            if dependency in dependents:
                dependents[dependency].add(step.step_id)

    roots = tuple(sorted(
        step.step_id
        for step in plan.steps
        if not step.depends_on
    ))
    leaves = tuple(sorted(
        step_id
        for step_id, children in dependents.items()
        if not children
    ))
    terminals = tuple(sorted(
        step.step_id for step in plan.steps if step.terminal
    ))

    if len(plan.steps) > policy.max_steps:
        reasons.append("step-budget-exceeded")
    if not roots:
        reasons.append("plan-has-no-root")
    if not terminals:
        reasons.append("plan-has-no-terminal-step")
    if policy.require_terminal_leaves:
        nonterminal_leaves = sorted(set(leaves) - set(terminals))
        if nonterminal_leaves:
            reasons.append(
                "nonterminal-leaves:" + ",".join(nonterminal_leaves)
            )
        terminal_nonleaves = sorted(
            set(terminals) - set(leaves)
        )
        if terminal_nonleaves:
            reasons.append(
                "terminal-step-has-dependents:"
                + ",".join(terminal_nonleaves)
            )

    total_tokens = sum(step.max_tokens for step in plan.steps)
    total_cost = sum(
        step.max_cost_units for step in plan.steps
    )
    total_time = sum(
        step.max_wall_time_s for step in plan.steps
    )
    if total_tokens > policy.max_total_tokens:
        reasons.append("token-budget-exceeded")
    if total_cost > policy.max_total_cost_units:
        reasons.append("cost-budget-exceeded")
    if total_time > policy.max_total_wall_time_s:
        reasons.append("wall-time-budget-exceeded")

    required_capabilities = tuple(sorted({
        capability
        for step in plan.steps
        for capability in step.required_capabilities
    }))
    forbidden = sorted(
        set(required_capabilities)
        - set(policy.allowed_capabilities)
    )
    if forbidden:
        reasons.append(
            "capability-not-allowed:" + ",".join(forbidden)
        )

    for step in plan.steps:
        if step.irreversible and not policy.allow_irreversible:
            reasons.append(
                f"irreversible-step-blocked:{step.step_id}"
            )

    produced = set(plan.initial_facts)
    facts_after: dict[str, set[str]] = {}
    if not graph_reasons:
        for step_id in order:
            step = steps[step_id]
            available = set(plan.initial_facts)
            for dependency in step.depends_on:
                available.update(facts_after[dependency])
            missing_facts = sorted(
                set(step.preconditions) - available
            )
            if missing_facts:
                reasons.append(
                    "unsatisfied-preconditions:"
                    + step.step_id
                    + ":"
                    + ",".join(missing_facts)
                )
            available.update(step.postconditions)
            facts_after[step_id] = available
            produced.update(step.postconditions)

    normalized = tuple(sorted(set(reasons)))
    return PlanAnalysisDecision(
        accepted=not normalized,
        reasons=normalized,
        plan_digest=plan.digest,
        policy_digest=policy.digest,
        topological_order=order,
        root_step_ids=roots,
        leaf_step_ids=leaves,
        terminal_step_ids=terminals,
        total_tokens=total_tokens,
        total_cost_units=total_cost,
        total_wall_time_s=total_time,
        produced_facts=tuple(sorted(produced)),
        required_capabilities=required_capabilities,
    )


def simulate_static_plan(
    plan: StaticPlanDefinition,
    analysis: PlanAnalysisDecision,
    *,
    available_capabilities: Iterable[str],
    injected_failure_step_id: str | None = None,
) -> PlanSimulationDecision:
    if not isinstance(plan, StaticPlanDefinition):
        raise TypeError("plan must be StaticPlanDefinition")
    if not isinstance(analysis, PlanAnalysisDecision):
        raise TypeError(
            "analysis must be PlanAnalysisDecision"
        )
    capabilities = set(
        _plan_tokens(
            available_capabilities,
            "available_capabilities",
            allow_empty=False,
        )
    )
    failure = (
        None
        if injected_failure_step_id is None
        else _plan_token(
            injected_failure_step_id,
            "injected_failure_step_id",
        )
    )

    reasons: list[str] = []
    if analysis.plan_digest != plan.digest:
        reasons.append("analysis-plan-digest-mismatch")
    if not analysis.accepted:
        reasons.append("static-analysis-rejected")

    steps = {step.step_id: step for step in plan.steps}
    if failure is not None and failure not in steps:
        reasons.append("injected-failure-step-missing")

    facts_after: dict[str, set[str]] = {}
    executed: list[str] = []
    recovered = False
    disposition = SimulationDisposition.COMPLETE
    final_facts = set(plan.initial_facts)

    if not reasons:
        for step_id in analysis.topological_order:
            step = steps[step_id]
            if any(
                dependency not in executed
                for dependency in step.depends_on
            ):
                reasons.append(
                    f"runtime-dependency-not-complete:{step_id}"
                )
                disposition = SimulationDisposition.BLOCKED
                break
            available = set(plan.initial_facts)
            for dependency in step.depends_on:
                available.update(facts_after[dependency])

            missing_caps = sorted(
                set(step.required_capabilities) - capabilities
            )
            if missing_caps:
                reasons.append(
                    "runtime-capability-missing:"
                    + step_id
                    + ":"
                    + ",".join(missing_caps)
                )
                disposition = SimulationDisposition.BLOCKED
                break
            missing_facts = sorted(
                set(step.preconditions) - available
            )
            if missing_facts:
                reasons.append(
                    "runtime-precondition-missing:"
                    + step_id
                    + ":"
                    + ",".join(missing_facts)
                )
                disposition = SimulationDisposition.BLOCKED
                break

            executed.append(step_id)
            if failure == step_id:
                if (
                    step.side_effect
                    and not step.irreversible
                    and step.recovery_plan_digest is not None
                    and step.rollback_test_digest is not None
                ):
                    recovered = True
                    disposition = (
                        SimulationDisposition.RECOVERED_FAILURE
                    )
                else:
                    reasons.append(f"unsafe-failure:{step_id}")
                    disposition = (
                        SimulationDisposition.UNSAFE_FAILURE
                    )
                break

            available.update(step.postconditions)
            facts_after[step_id] = available
            final_facts.update(step.postconditions)

    if reasons and disposition is SimulationDisposition.COMPLETE:
        disposition = SimulationDisposition.BLOCKED

    accepted = (
        not reasons
        and disposition in {
            SimulationDisposition.COMPLETE,
            SimulationDisposition.RECOVERED_FAILURE,
        }
    )
    return PlanSimulationDecision(
        accepted=accepted,
        disposition=disposition,
        reasons=tuple(sorted(set(reasons))),
        plan_digest=plan.digest,
        analysis_digest=analysis.decision_digest,
        executed_step_ids=tuple(executed),
        final_facts=tuple(sorted(final_facts)),
        injected_failure_step_id=failure,
        recovered=recovered,
    )


def _plan_risk_digest(
    risk_evaluation: RiskBindingEvaluation | None,
) -> str | None:
    if risk_evaluation is None:
        return None
    if not isinstance(risk_evaluation, RiskBindingEvaluation):
        raise TypeError(
            "risk_evaluation must be RiskBindingEvaluation"
        )
    return _plan_digest(risk_evaluation.as_dict())


def qualify_static_plan(
    *,
    plan: StaticPlanDefinition,
    verification_policy: PlanVerificationPolicy,
    reasoning_policy: ReasoningPolicy,
    analysis: PlanAnalysisDecision,
    simulation: PlanSimulationDecision,
    stopping: StoppingDecision,
    risk_evaluation: RiskBindingEvaluation | None = None,
) -> PlanQualificationDecision:
    if not isinstance(plan, StaticPlanDefinition):
        raise TypeError("plan must be StaticPlanDefinition")
    if not isinstance(
        verification_policy,
        PlanVerificationPolicy,
    ):
        raise TypeError(
            "verification_policy must be PlanVerificationPolicy"
        )
    if not isinstance(reasoning_policy, ReasoningPolicy):
        raise TypeError(
            "reasoning_policy must be ReasoningPolicy"
        )
    if not isinstance(analysis, PlanAnalysisDecision):
        raise TypeError(
            "analysis must be PlanAnalysisDecision"
        )
    if not isinstance(simulation, PlanSimulationDecision):
        raise TypeError(
            "simulation must be PlanSimulationDecision"
        )
    if not isinstance(stopping, StoppingDecision):
        raise TypeError("stopping must be StoppingDecision")

    reasons: list[str] = []
    if plan.reasoning_policy_digest != reasoning_policy.digest:
        reasons.append("reasoning-policy-digest-mismatch")
    if stopping.policy_digest != reasoning_policy.digest:
        reasons.append("stopping-policy-digest-mismatch")
    if plan.planning_history_digest != stopping.history_digest:
        reasons.append("planning-history-digest-mismatch")
    if stopping.disposition is not StopDisposition.COMPLETE:
        reasons.append("planning-search-not-complete")

    if analysis.plan_digest != plan.digest:
        reasons.append("analysis-plan-digest-mismatch")
    if analysis.policy_digest != verification_policy.digest:
        reasons.append("analysis-policy-digest-mismatch")
    if not analysis.accepted:
        reasons.append("static-analysis-rejected")

    if simulation.plan_digest != plan.digest:
        reasons.append("simulation-plan-digest-mismatch")
    if simulation.analysis_digest != analysis.decision_digest:
        reasons.append(
            "simulation-analysis-digest-mismatch"
        )
    if not simulation.accepted:
        reasons.append("simulation-rejected")
    if (
        simulation.disposition
        is SimulationDisposition.UNSAFE_FAILURE
    ):
        reasons.append("simulation-unsafe-failure")

    if plan.risk in {
        ReasoningRisk.HIGH,
        ReasoningRisk.CRITICAL,
    }:
        if risk_evaluation is None:
            reasons.append("risk-binding-missing")
        else:
            if not isinstance(
                risk_evaluation,
                RiskBindingEvaluation,
            ):
                raise TypeError(
                    "risk_evaluation must be RiskBindingEvaluation"
                )
            if (
                not risk_evaluation.resolved
                or risk_evaluation.blockers
            ):
                reasons.append("risk-binding-unresolved")
            if plan.risk is ReasoningRisk.CRITICAL:
                if risk_evaluation.severity != "critical":
                    reasons.append(
                        "critical-risk-classification-mismatch"
                    )
            elif risk_evaluation.severity not in {
                "high",
                "critical",
            }:
                reasons.append(
                    "high-risk-classification-mismatch"
                )

    normalized = tuple(sorted(set(reasons)))
    return PlanQualificationDecision(
        accepted=not normalized,
        reasons=normalized,
        plan_digest=plan.digest,
        verification_policy_digest=verification_policy.digest,
        reasoning_policy_digest=reasoning_policy.digest,
        analysis_digest=analysis.decision_digest,
        simulation_digest=simulation.decision_digest,
        stopping_digest=stopping.decision_digest,
        risk_evaluation_digest=_plan_risk_digest(
            risk_evaluation
        ),
    )
