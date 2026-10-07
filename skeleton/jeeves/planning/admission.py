from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json

from .constraints import Constraint, ConstraintReport, validate_constraints
from .models import Plan, PlanState, RiskTier, topological_order


class AdmissionDecision(str, Enum):
    ACCEPT = "accept"
    HOLD = "hold"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class AdmissionPolicy:
    maximum_risk: RiskTier = RiskTier.HIGH
    require_evidence: bool = True
    require_constraints: bool = True
    allow_empty_assumptions: bool = True
    max_steps: int = 256

    def __post_init__(self) -> None:
        if not isinstance(self.maximum_risk, RiskTier):
            raise ValueError("maximum_risk must be a risk tier")
        if not isinstance(self.require_evidence, bool) or not isinstance(self.require_constraints, bool) or not isinstance(self.allow_empty_assumptions, bool):
            raise ValueError("admission flags must be boolean")
        if isinstance(self.max_steps, bool) or not isinstance(self.max_steps, int) or not 1 <= self.max_steps <= 256:
            raise ValueError("max_steps must be an integer from 1 to 256")


@dataclass(frozen=True, slots=True)
class AdmissionFinding:
    code: str
    message: str
    blocking: bool = True


@dataclass(frozen=True, slots=True)
class AdmissionResult:
    decision: AdmissionDecision
    plan_id: str
    order: tuple[str, ...]
    findings: tuple[AdmissionFinding, ...]
    constraint_report: ConstraintReport | None = None

    @property
    def admitted(self) -> bool:
        return self.decision is AdmissionDecision.ACCEPT


def _digest_payload(plan: Plan, policy: AdmissionPolicy, constraints: tuple[Constraint, ...]) -> str:
    payload = {"plan": plan.to_dict(), "policy": policy.__dict__ if hasattr(policy, "__dict__") else {"maximum_risk": policy.maximum_risk.value, "require_evidence": policy.require_evidence, "require_constraints": policy.require_constraints, "allow_empty_assumptions": policy.allow_empty_assumptions, "max_steps": policy.max_steps}, "constraints": [c.__dict__ if hasattr(c, "__dict__") else {"name": c.name, "kind": c.kind.value, "limit": c.limit, "value": c.value} for c in constraints]}
    return sha256(json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()


def admit(plan: Plan, policy: AdmissionPolicy = AdmissionPolicy(), constraints: tuple[Constraint, ...] = ()) -> AdmissionResult:
    findings: list[AdmissionFinding] = []
    if len(plan.steps) > policy.max_steps:
        findings.append(AdmissionFinding("step_budget", "plan exceeds configured step budget"))
    if policy.require_evidence and any(not step.evidence_required for step in plan.steps):
        findings.append(AdmissionFinding("evidence", "one or more steps lack required evidence"))
    if not policy.allow_empty_assumptions and not plan.assumptions:
        findings.append(AdmissionFinding("assumptions", "explicit assumptions are required"))
    order = topological_order(plan)
    report = validate_constraints(plan, constraints) if policy.require_constraints or constraints else None
    if report and not report.valid:
        findings.extend(AdmissionFinding("constraint", v.reason) for v in report.violations)
    risk_order = {RiskTier.LOW: 0, RiskTier.MEDIUM: 1, RiskTier.HIGH: 2, RiskTier.CRITICAL: 3}
    if any(risk_order[s.risk] > risk_order[policy.maximum_risk] for s in plan.steps):
        findings.append(AdmissionFinding("risk", "plan exceeds risk ceiling"))
    if plan.state not in {PlanState.DRAFT, PlanState.READY}:
        findings.append(AdmissionFinding("state", "plan is not admissible from its current state"))
    decision = AdmissionDecision.REJECT if any(f.blocking for f in findings) else AdmissionDecision.ACCEPT
    return AdmissionResult(decision, plan.id, order, tuple(findings), report)


def explain(result: AdmissionResult) -> tuple[str, ...]:
    if not result.findings:
        return ("plan satisfies admission checks",)
    return tuple(f"{f.code}: {f.message}" for f in result.findings)


def admission_fingerprint(plan: Plan, policy: AdmissionPolicy, constraints: tuple[Constraint, ...] = ()) -> str:
    return _digest_payload(plan, policy, constraints)
