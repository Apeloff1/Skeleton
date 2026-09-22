"""Mandatory runtime enforcement bridge for Jeeves tool execution.

This module closes the architectural gap between Jeeves' evidence-first runtime
and the newer epistemic planning/authorization stack. The core runtime can use
one object for the entire consequential path:

    host policy -> exact intent binding -> epistemic decision
      -> one-time authorization -> existing ToolExecutor
      -> verified evidence -> transition learning -> tamper-evident audit

The guard deliberately does *not* replace the existing host execution policy or
capability grants. It composes with them. A tool call must first be allowed by
``ExecutionPolicy`` and still passes through ``ToolExecutor`` grants, schema
validation, budgets, timeout and evidence creation. The guard adds a second,
stateful epistemic authorization layer around that path.

Cold start is explicit rather than hidden. Low-risk calls can be admitted under
trusted host policy before a transition model has observations. Mutating and
external cold starts additionally require the exact runtime confirmation token.
High-impact cold starts are denied. Every cold-start admission is recorded in
the audit ledger and immediately becomes real transition data only after the
runtime verifier reports the outcome.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Mapping, Sequence

from .epistemic_authorization import AuthorizationPolicy, DecisionAuthorizer
from .epistemic_planning import (
    ActionCandidate,
    DecisionDisposition,
    DecisionPolicy,
    EpistemicDecision,
    EpistemicDecisionBridge,
)
from .epistemic_tool_gate import (
    BoundToolExecution,
    PermitBoundToolExecutor,
    ToolExecutionIntent,
    bind_intent_metadata,
)
from .execution_audit import (
    AuditEventKind,
    AuditSeverity,
    ExecutionAuditCheckpoint,
    ExecutionAuditError,
    GENESIS_HASH,
    InMemoryExecutionAuditStore,
    ReplayReport,
)
from .model_based_control import (
    AbstractAction,
    CompactState,
    LearnedTransitionModel,
    PredictedTransition,
    TransitionExperience,
    TransitionOutcome,
    transition_experience,
)
from .policy import PolicyDecision
from .tools import ToolExecutionContext, ToolExecutor, ToolGrant, ToolSpec
from .types import (
    AgentContractError,
    Budget,
    Decision,
    RiskTier,
    ToolCall,
    ToolObservation,
    Usage,
    finite_number,
    json_safe,
    non_negative_int,
    probability,
    require_id,
    stable_fingerprint,
    stable_id,
)
from .world_model import BeliefGraph


class RuntimeGuardError(RuntimeError):
    """Base error for runtime epistemic enforcement."""


class RuntimeGuardDenied(RuntimeGuardError):
    """Raised when a host-allowed call fails the epistemic guard."""

    def __init__(
        self,
        message: str,
        *,
        disposition: DecisionDisposition | None = None,
        operation_id: str | None = None,
        decision_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.disposition = disposition
        self.operation_id = operation_id
        self.decision_id = decision_id


class GuardAdmissionMode(str, Enum):
    MODEL_GATED = "model_gated"
    COLD_START_HOST_TRUST = "cold_start_host_trust"


@dataclass(frozen=True, slots=True)
class RiskGuardProfile:
    risk: RiskTier
    minimum_observations: int
    maximum_model_uncertainty: float
    minimum_verification: float
    minimum_lower_utility: float
    maximum_regret: float
    require_stress_survival: bool
    require_nonnegative_joint_adverse: bool
    allow_cold_start: bool
    cold_start_requires_confirmation: bool
    intrinsic_value: float = 0.1

    def __post_init__(self) -> None:
        if not isinstance(self.risk, RiskTier):
            object.__setattr__(self, "risk", RiskTier(str(self.risk)))
        object.__setattr__(
            self,
            "minimum_observations",
            non_negative_int(
                "minimum_observations",
                self.minimum_observations,
                maximum=1_000_000,
            ),
        )
        for name in (
            "maximum_model_uncertainty",
            "minimum_verification",
            "maximum_regret",
        ):
            object.__setattr__(self, name, probability(name, getattr(self, name)))
        lower = finite_number("minimum_lower_utility", self.minimum_lower_utility)
        if not -2.0 <= lower <= 2.0:
            raise AgentContractError("minimum_lower_utility must be in [-2, 2]")
        object.__setattr__(self, "minimum_lower_utility", lower)
        intrinsic = finite_number("intrinsic_value", self.intrinsic_value)
        if not -1.0 <= intrinsic <= 1.0:
            raise AgentContractError("intrinsic_value must be in [-1, 1]")
        object.__setattr__(self, "intrinsic_value", intrinsic)

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "risk": self.risk.value,
                "minimum_observations": self.minimum_observations,
                "maximum_model_uncertainty": self.maximum_model_uncertainty,
                "minimum_verification": self.minimum_verification,
                "minimum_lower_utility": self.minimum_lower_utility,
                "maximum_regret": self.maximum_regret,
                "require_stress_survival": self.require_stress_survival,
                "require_nonnegative_joint_adverse": self.require_nonnegative_joint_adverse,
                "allow_cold_start": self.allow_cold_start,
                "cold_start_requires_confirmation": self.cold_start_requires_confirmation,
                "intrinsic_value": self.intrinsic_value,
            }
        )


@dataclass(frozen=True, slots=True)
class RuntimeGuardPolicy:
    enabled: bool = True
    fail_closed_on_audit_error: bool = True
    token_ttl_seconds: float = 30.0
    read_only: RiskGuardProfile = field(
        default_factory=lambda: RiskGuardProfile(
            risk=RiskTier.READ_ONLY,
            minimum_observations=1,
            maximum_model_uncertainty=1.0,
            minimum_verification=0.0,
            minimum_lower_utility=-0.50,
            maximum_regret=1.0,
            require_stress_survival=False,
            require_nonnegative_joint_adverse=False,
            allow_cold_start=True,
            cold_start_requires_confirmation=False,
            intrinsic_value=0.15,
        )
    )
    reversible: RiskGuardProfile = field(
        default_factory=lambda: RiskGuardProfile(
            risk=RiskTier.REVERSIBLE,
            minimum_observations=1,
            maximum_model_uncertainty=0.95,
            minimum_verification=0.20,
            minimum_lower_utility=-0.25,
            maximum_regret=0.85,
            require_stress_survival=False,
            require_nonnegative_joint_adverse=False,
            allow_cold_start=True,
            cold_start_requires_confirmation=False,
            intrinsic_value=0.15,
        )
    )
    mutating: RiskGuardProfile = field(
        default_factory=lambda: RiskGuardProfile(
            risk=RiskTier.MUTATING,
            minimum_observations=2,
            maximum_model_uncertainty=0.82,
            minimum_verification=0.50,
            minimum_lower_utility=-0.05,
            maximum_regret=0.55,
            require_stress_survival=True,
            require_nonnegative_joint_adverse=False,
            allow_cold_start=True,
            cold_start_requires_confirmation=True,
            intrinsic_value=0.10,
        )
    )
    external: RiskGuardProfile = field(
        default_factory=lambda: RiskGuardProfile(
            risk=RiskTier.EXTERNAL,
            minimum_observations=3,
            maximum_model_uncertainty=0.72,
            minimum_verification=0.62,
            minimum_lower_utility=0.0,
            maximum_regret=0.40,
            require_stress_survival=True,
            require_nonnegative_joint_adverse=False,
            allow_cold_start=True,
            cold_start_requires_confirmation=True,
            intrinsic_value=0.05,
        )
    )
    high_impact: RiskGuardProfile = field(
        default_factory=lambda: RiskGuardProfile(
            risk=RiskTier.HIGH_IMPACT,
            minimum_observations=8,
            maximum_model_uncertainty=0.45,
            minimum_verification=0.82,
            minimum_lower_utility=0.15,
            maximum_regret=0.20,
            require_stress_survival=True,
            require_nonnegative_joint_adverse=True,
            allow_cold_start=False,
            cold_start_requires_confirmation=True,
            intrinsic_value=0.0,
        )
    )

    def __post_init__(self) -> None:
        ttl = finite_number("token_ttl_seconds", self.token_ttl_seconds)
        if not 0.01 <= ttl <= 86_400.0:
            raise AgentContractError("token_ttl_seconds must be in [0.01, 86400]")
        object.__setattr__(self, "token_ttl_seconds", ttl)
        profiles = (
            self.read_only,
            self.reversible,
            self.mutating,
            self.external,
            self.high_impact,
        )
        expected = (
            RiskTier.READ_ONLY,
            RiskTier.REVERSIBLE,
            RiskTier.MUTATING,
            RiskTier.EXTERNAL,
            RiskTier.HIGH_IMPACT,
        )
        if tuple(profile.risk for profile in profiles) != expected:
            raise AgentContractError("runtime guard risk profiles are misconfigured")

    def profile(self, risk: RiskTier) -> RiskGuardProfile:
        if not isinstance(risk, RiskTier):
            risk = RiskTier(str(risk))
        return {
            RiskTier.READ_ONLY: self.read_only,
            RiskTier.REVERSIBLE: self.reversible,
            RiskTier.MUTATING: self.mutating,
            RiskTier.EXTERNAL: self.external,
            RiskTier.HIGH_IMPACT: self.high_impact,
        }[risk]

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "enabled": self.enabled,
                "fail_closed_on_audit_error": self.fail_closed_on_audit_error,
                "token_ttl_seconds": self.token_ttl_seconds,
                "profiles": [
                    self.profile(risk).fingerprint
                    for risk in (
                        RiskTier.READ_ONLY,
                        RiskTier.REVERSIBLE,
                        RiskTier.MUTATING,
                        RiskTier.EXTERNAL,
                        RiskTier.HIGH_IMPACT,
                    )
                ],
            }
        )


@dataclass(frozen=True, slots=True)
class RuntimeGuardSignals:
    progress: float
    uncertainty: float
    budget_pressure: float
    failure_pressure: float
    terminal: bool = False

    def __post_init__(self) -> None:
        for name in (
            "progress",
            "uncertainty",
            "budget_pressure",
            "failure_pressure",
        ):
            object.__setattr__(self, name, probability(name, getattr(self, name)))


@dataclass(frozen=True, slots=True)
class RuntimeGuardRequest:
    run_id: str
    goal_id: str
    step_id: str
    attempt: int
    plan_version: int
    call: ToolCall
    execution_context: ToolExecutionContext
    tool_spec: ToolSpec
    grants: tuple[ToolGrant, ...]
    host_policy_decision: PolicyDecision
    confirmed_actions: tuple[str, ...]
    usage: Usage
    budget: Budget
    signals: RuntimeGuardSignals
    evidence_ids: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("run_id", "goal_id", "step_id"):
            object.__setattr__(self, name, require_id(name, getattr(self, name)))
        object.__setattr__(
            self,
            "attempt",
            non_negative_int("attempt", self.attempt, maximum=1000),
        )
        object.__setattr__(
            self,
            "plan_version",
            non_negative_int("plan_version", self.plan_version, maximum=100_000),
        )
        if not isinstance(self.call, ToolCall):
            raise AgentContractError("call must be ToolCall")
        if not isinstance(self.execution_context, ToolExecutionContext):
            raise AgentContractError("execution_context must be ToolExecutionContext")
        if not isinstance(self.tool_spec, ToolSpec):
            raise AgentContractError("tool_spec must be ToolSpec")
        grants = tuple(self.grants)
        if any(not isinstance(item, ToolGrant) for item in grants):
            raise AgentContractError("grants must contain ToolGrant")
        object.__setattr__(self, "grants", grants)
        if not isinstance(self.host_policy_decision, PolicyDecision):
            raise AgentContractError("host_policy_decision must be PolicyDecision")
        object.__setattr__(
            self,
            "confirmed_actions",
            tuple(require_id("confirmed_action", item) for item in self.confirmed_actions),
        )
        if not isinstance(self.usage, Usage):
            raise AgentContractError("usage must be Usage")
        if not isinstance(self.budget, Budget):
            raise AgentContractError("budget must be Budget")
        if not isinstance(self.signals, RuntimeGuardSignals):
            raise AgentContractError("signals must be RuntimeGuardSignals")
        object.__setattr__(
            self,
            "evidence_ids",
            tuple(require_id("evidence_id", item) for item in self.evidence_ids),
        )
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))
        if self.call.name != self.tool_spec.name:
            raise AgentContractError("call/tool spec name mismatch")
        if self.execution_context.run_id != self.run_id:
            raise AgentContractError("execution context run id mismatch")


@dataclass(frozen=True, slots=True)
class GuardedToolExecution:
    operation_id: str
    request_fingerprint: str
    request: RuntimeGuardRequest
    admission_mode: GuardAdmissionMode
    profile_fingerprint: str
    intent: ToolExecutionIntent
    action: AbstractAction
    pre_state: CompactState
    prediction: PredictedTransition
    decision: EpistemicDecision
    bound_execution: BoundToolExecution
    observation_fingerprint: str
    audit_head_after_observation: str
    fingerprint: str

    @property
    def observation(self) -> ToolObservation:
        return self.bound_execution.observation


@dataclass(frozen=True, slots=True)
class GuardFinalization:
    run_id: str
    operation_id: str
    outcome: TransitionOutcome
    verification_score: float
    evidence_ids: tuple[str, ...]
    evidence_fingerprint: str
    next_state: CompactState
    experience: TransitionExperience
    model_fingerprint: str
    audit_checkpoint: ExecutionAuditCheckpoint
    fingerprint: str


class RuntimeEpistemicGuard:
    """Stateful guard used by the main runtime for every host-allowed tool call."""

    def __init__(
        self,
        tool_executor: ToolExecutor,
        *,
        policy: RuntimeGuardPolicy | None = None,
        world: BeliefGraph | None = None,
        transition_model: LearnedTransitionModel | None = None,
        audit_store: InMemoryExecutionAuditStore | None = None,
        wall_clock: Callable[[], float] = time.time,
    ) -> None:
        if not isinstance(tool_executor, ToolExecutor):
            raise TypeError("tool_executor must be ToolExecutor")
        self.tool_executor = tool_executor
        self.policy = policy or RuntimeGuardPolicy()
        self.world = world or BeliefGraph(clock=wall_clock)
        self.transition_model = transition_model or LearnedTransitionModel()
        self.audit_store = audit_store or InMemoryExecutionAuditStore(clock=wall_clock)
        self._wall_clock = wall_clock
        self.authorizer = DecisionAuthorizer(
            self.world,
            self.transition_model,
            policy=AuthorizationPolicy(token_ttl_seconds=self.policy.token_ttl_seconds),
            clock=wall_clock,
        )
        self.permit_executor = PermitBoundToolExecutor(self.authorizer, tool_executor)
        self._reserved: set[str] = set()
        self._pending: dict[str, GuardedToolExecution] = {}
        self._finalized: dict[str, GuardFinalization] = {}
        self._lock = threading.RLock()

    def execute(self, request: RuntimeGuardRequest) -> GuardedToolExecution:
        if not isinstance(request, RuntimeGuardRequest):
            raise TypeError("request must be RuntimeGuardRequest")
        if request.host_policy_decision.decision is not Decision.ALLOW:
            raise RuntimeGuardDenied(
                "runtime guard refuses a call not already allowed by host policy"
            )
        if not self.policy.enabled:
            raise RuntimeGuardDenied("runtime epistemic guard is disabled")

        ledger = self.audit_store.get_or_create(request.run_id)
        request_fingerprint = self._request_fingerprint(request)
        action_id = stable_id(
            "tool_action",
            {
                "tool": request.call.name,
                "arguments": stable_fingerprint(request.call.arguments),
                "risk": request.tool_spec.risk.value,
            },
        )
        intent = ToolExecutionIntent.bind(
            action_id=action_id,
            call=request.call,
            context=request.execution_context,
            metadata={
                "goal_id": request.goal_id,
                "step_id": request.step_id,
                "attempt": request.attempt,
                "plan_version": request.plan_version,
                "request_fingerprint": request_fingerprint,
            },
        )
        operation_id = stable_id(
            "guard_op",
            {
                "run": request.run_id,
                "step": request.step_id,
                "attempt": request.attempt,
                "intent": intent.fingerprint,
            },
        )
        self._reserve_operation(operation_id)
        try:
            return self._execute_reserved(
                request,
                ledger=ledger,
                request_fingerprint=request_fingerprint,
                action_id=action_id,
                intent=intent,
                operation_id=operation_id,
            )
        except Exception:
            with self._lock:
                self._reserved.discard(operation_id)
            raise

    def _execute_reserved(
        self,
        request: RuntimeGuardRequest,
        *,
        ledger,
        request_fingerprint: str,
        action_id: str,
        intent: ToolExecutionIntent,
        operation_id: str,
    ) -> GuardedToolExecution:
        action = AbstractAction(
            action_id=action_id,
            name=f"tool:{request.call.name}",
            capability=request.call.name,
            risk=request.tool_spec.risk,
            estimated_external_cost=0.0,
            reversible=request.tool_spec.risk in {
                RiskTier.READ_ONLY,
                RiskTier.REVERSIBLE,
            },
            metadata=bind_intent_metadata(
                {
                    "goal_id": request.goal_id,
                    "step_id": request.step_id,
                    "plan_version": request.plan_version,
                },
                intent,
            ),
        )
        pre_state = self._compact_state(request, phase="pre")
        prediction = self.transition_model.predict(pre_state.state_id, action.action_id)
        profile = self.policy.profile(request.tool_spec.risk)

        self._audit(
            ledger,
            AuditEventKind.INTENT_BOUND,
            operation_id,
            {
                "intent_id": intent.intent_id,
                "intent_fingerprint": intent.fingerprint,
                "request_fingerprint": request_fingerprint,
                "call_id": request.call.call_id,
                "tool_name": request.call.name,
                "argument_fingerprint": intent.argument_fingerprint,
                "user_id": request.execution_context.user_id,
                "trace_id": request.execution_context.trace_id,
                "action_id": action.action_id,
                "risk": action.risk.value,
                "state_id": pre_state.state_id,
                "state_fingerprint": pre_state.fingerprint,
                "model_fingerprint": self.transition_model.fingerprint,
                "world_fingerprint": self.world.snapshot(persist=False).fingerprint,
                "profile_fingerprint": profile.fingerprint,
            },
            severity=AuditSeverity.SECURITY,
        )

        decision, admission_mode = self._decision(
            request,
            action=action,
            state=pre_state,
            prediction=prediction,
            profile=profile,
        )
        self._audit(
            ledger,
            AuditEventKind.DECISION_MADE,
            operation_id,
            {
                "decision_id": decision.decision_id,
                "decision_fingerprint": decision.fingerprint,
                "disposition": decision.disposition.value,
                "admission_mode": admission_mode.value,
                "reasons": list(decision.reasons),
                "policy_fingerprint": decision.policy_fingerprint,
                "world_fingerprint": decision.world_fingerprint,
                "model_fingerprint": decision.model_fingerprint,
                "prediction_observations": prediction.observations,
                "prediction_uncertainty": prediction.uncertainty,
                "prediction_expected_verification": prediction.expected_verification,
            },
            severity=AuditSeverity.SECURITY,
        )
        if decision.disposition is not DecisionDisposition.ACT or decision.selected_action is None:
            self._audit(
                ledger,
                AuditEventKind.EXECUTION_DENIED,
                operation_id,
                {
                    "reason": "epistemic decision did not authorize action",
                    "disposition": decision.disposition.value,
                    "decision_id": decision.decision_id,
                    "decision_fingerprint": decision.fingerprint,
                },
                severity=AuditSeverity.WARNING,
            )
            raise RuntimeGuardDenied(
                "epistemic guard chose " + decision.disposition.value,
                disposition=decision.disposition,
                operation_id=operation_id,
                decision_id=decision.decision_id,
            )

        issued = self.authorizer.issue(
            decision,
            expected_policy_fingerprint=decision.policy_fingerprint,
            metadata={
                "operation_id": operation_id,
                "request_fingerprint": request_fingerprint,
                "intent_fingerprint": intent.fingerprint,
                "admission_mode": admission_mode.value,
            },
        )
        if not issued.allowed or issued.token is None:
            self._audit(
                ledger,
                AuditEventKind.EXECUTION_FAILED,
                operation_id,
                {
                    "reason": "authorization issue rejected",
                    "failures": [item.value for item in issued.failures],
                    "authorization_fingerprint": issued.fingerprint,
                },
                severity=AuditSeverity.ERROR,
            )
            raise RuntimeGuardDenied(
                "decision authorization failed: "
                + ",".join(item.value for item in issued.failures),
                disposition=decision.disposition,
                operation_id=operation_id,
                decision_id=decision.decision_id,
            )
        self._audit(
            ledger,
            AuditEventKind.AUTHORIZATION_ISSUED,
            operation_id,
            {
                "token_id": issued.token.token_id,
                "decision_id": decision.decision_id,
                "authorization_fingerprint": issued.fingerprint,
                "token_fingerprint": issued.token.token_fingerprint,
                "expires_at": issued.token.expires_at,
            },
            severity=AuditSeverity.SECURITY,
        )

        try:
            bound = self.permit_executor.execute(
                issued.token,
                intent,
                request.call,
                request.execution_context,
                grants=request.grants,
                expected_policy_fingerprint=decision.policy_fingerprint,
            )
        except Exception as exc:
            self._audit(
                ledger,
                AuditEventKind.EXECUTION_FAILED,
                operation_id,
                {
                    "reason": "permit-bound tool execution failed",
                    "error": f"{type(exc).__name__}: {str(exc)[:2048]}",
                    "token_id": issued.token.token_id,
                },
                severity=AuditSeverity.ERROR,
            )
            raise

        self._audit(
            ledger,
            AuditEventKind.AUTHORIZATION_CONSUMED,
            operation_id,
            {
                "token_id": issued.token.token_id,
                "permit_id": bound.permit.permit_id,
                "decision_id": decision.decision_id,
                "authorization_fingerprint": bound.authorization.fingerprint,
                "permit_fingerprint": bound.permit.permit_fingerprint,
            },
            severity=AuditSeverity.SECURITY,
        )
        observation_fingerprint = self._observation_fingerprint(bound.observation)
        self._audit(
            ledger,
            AuditEventKind.TOOL_OBSERVED,
            operation_id,
            {
                "call_id": request.call.call_id,
                "tool_name": request.call.name,
                "observation_fingerprint": observation_fingerprint,
                "ok": bound.observation.ok,
                "cached": bound.observation.cached,
                "evidence_ids": [ref.evidence_id for ref in bound.observation.evidence],
                "latency_ms": bound.observation.latency_ms,
                "bound_execution_fingerprint": bound.fingerprint,
            },
            severity=AuditSeverity.INFO if bound.observation.ok else AuditSeverity.WARNING,
        )
        fingerprint = stable_fingerprint(
            {
                "operation_id": operation_id,
                "request": request_fingerprint,
                "mode": admission_mode.value,
                "profile": profile.fingerprint,
                "intent": intent.fingerprint,
                "action": action.action_id,
                "state": pre_state.fingerprint,
                "prediction": self._prediction_fingerprint(prediction),
                "decision": decision.fingerprint,
                "bound_execution": bound.fingerprint,
                "observation": observation_fingerprint,
                "audit_head": ledger.head_hash,
            }
        )
        execution = GuardedToolExecution(
            operation_id=operation_id,
            request_fingerprint=request_fingerprint,
            request=request,
            admission_mode=admission_mode,
            profile_fingerprint=profile.fingerprint,
            intent=intent,
            action=action,
            pre_state=pre_state,
            prediction=prediction,
            decision=decision,
            bound_execution=bound,
            observation_fingerprint=observation_fingerprint,
            audit_head_after_observation=ledger.head_hash,
            fingerprint=fingerprint,
        )
        with self._lock:
            if operation_id not in self._reserved:
                raise RuntimeGuardError("guarded operation reservation disappeared")
            self._reserved.discard(operation_id)
            self._pending[operation_id] = execution
        return execution

    def finalize(
        self,
        execution: GuardedToolExecution,
        *,
        verification_score: float,
        outcome: TransitionOutcome,
        evidence_ids: Sequence[str],
        evidence_fingerprint: str,
        signals: RuntimeGuardSignals,
        cost: float = 0.0,
    ) -> GuardFinalization:
        if not isinstance(execution, GuardedToolExecution):
            raise TypeError("execution must be GuardedToolExecution")
        if not isinstance(outcome, TransitionOutcome):
            outcome = TransitionOutcome(str(outcome))
        verification_score = probability("verification_score", verification_score)
        cost = finite_number("cost", cost)
        if cost < 0:
            raise AgentContractError("cost must be non-negative")
        evidence_ids_tuple = tuple(require_id("evidence_id", item) for item in evidence_ids)
        evidence_fingerprint = self._hex_fingerprint(
            "evidence_fingerprint",
            evidence_fingerprint,
        )
        if not isinstance(signals, RuntimeGuardSignals):
            raise TypeError("signals must be RuntimeGuardSignals")

        with self._lock:
            pending = self._pending.get(execution.operation_id)
            if pending is None:
                prior = self._finalized.get(execution.operation_id)
                if prior is not None:
                    raise RuntimeGuardError("guarded operation already finalized")
                raise RuntimeGuardError("guarded operation is not pending")
            if pending.fingerprint != execution.fingerprint:
                raise RuntimeGuardError("pending guarded execution fingerprint mismatch")

        ledger = self.audit_store.get_or_create(execution.request.run_id)
        self._audit(
            ledger,
            AuditEventKind.EVIDENCE_INGESTED,
            execution.operation_id,
            {
                "evidence_ids": list(evidence_ids_tuple),
                "evidence_fingerprint": evidence_fingerprint,
                "observation_fingerprint": execution.observation_fingerprint,
            },
        )
        next_state = self._compact_state(
            execution.request,
            phase="post",
            signals=signals,
            extra_features={
                "outcome": outcome.value,
                "verified": str(verification_score >= 0.5).lower(),
            },
        )
        reward = self._reward(outcome, verification_score)
        experience = transition_experience(
            run_id=execution.request.run_id,
            state=execution.pre_state,
            action=execution.action,
            next_state=next_state,
            outcome=outcome,
            reward=reward,
            verification_score=verification_score,
            cost=cost,
            latency_ms=execution.observation.latency_ms,
            observed_at=self._wall_clock(),
            evidence_ids=evidence_ids_tuple,
            metadata={
                "operation_id": execution.operation_id,
                "guarded_execution_fingerprint": execution.fingerprint,
                "observation_fingerprint": execution.observation_fingerprint,
                "admission_mode": execution.admission_mode.value,
            },
        )
        predicted_next = self._most_likely_next(execution.prediction)
        if predicted_next is not None and execution.prediction.observations > 0:
            self.transition_model.record_prediction_error(
                execution.pre_state.state_id,
                execution.action.action_id,
                predicted_next=predicted_next,
                actual_next=next_state.state_id,
            )
        self.transition_model.observe(experience)
        model_fingerprint = self.transition_model.fingerprint
        self._audit(
            ledger,
            AuditEventKind.TRANSITION_LEARNED,
            execution.operation_id,
            {
                "experience_id": experience.experience_id,
                "state_id": experience.state.state_id,
                "action_id": experience.action.action_id,
                "next_state_id": experience.next_state.state_id,
                "outcome": experience.outcome.value,
                "reward": experience.reward,
                "verification_score": experience.verification_score,
                "model_fingerprint": model_fingerprint,
                "prediction_observations_before": execution.prediction.observations,
            },
        )
        self._audit(
            ledger,
            AuditEventKind.EXECUTION_FINALIZED,
            execution.operation_id,
            {
                "outcome": outcome.value,
                "verification_score": verification_score,
                "experience_id": experience.experience_id,
                "model_fingerprint": model_fingerprint,
                "evidence_fingerprint": evidence_fingerprint,
            },
            severity=AuditSeverity.INFO if outcome is TransitionOutcome.SUCCESS else AuditSeverity.WARNING,
        )
        checkpoint = ledger.checkpoint()
        fingerprint = stable_fingerprint(
            {
                "run_id": execution.request.run_id,
                "operation": execution.operation_id,
                "execution": execution.fingerprint,
                "outcome": outcome.value,
                "verification": verification_score,
                "evidence": evidence_fingerprint,
                "next_state": next_state.fingerprint,
                "experience": experience.experience_id,
                "model": model_fingerprint,
                "audit": checkpoint.checkpoint_fingerprint,
            }
        )
        result = GuardFinalization(
            run_id=execution.request.run_id,
            operation_id=execution.operation_id,
            outcome=outcome,
            verification_score=verification_score,
            evidence_ids=evidence_ids_tuple,
            evidence_fingerprint=evidence_fingerprint,
            next_state=next_state,
            experience=experience,
            model_fingerprint=model_fingerprint,
            audit_checkpoint=checkpoint,
            fingerprint=fingerprint,
        )
        with self._lock:
            self._pending.pop(execution.operation_id, None)
            self._finalized[execution.operation_id] = result
        return result

    def audit_checkpoint(self, run_id: str) -> ExecutionAuditCheckpoint:
        return self.audit_store.get_or_create(run_id).checkpoint()

    def verify_audit(
        self,
        run_id: str,
        *,
        expected_checkpoint: ExecutionAuditCheckpoint | None = None,
        require_finalized_operations: bool = False,
    ) -> ReplayReport:
        report = self.audit_store.verify(
            run_id,
            expected_checkpoint=expected_checkpoint,
            require_finalized_operations=require_finalized_operations,
        )
        if not report.valid and self.policy.fail_closed_on_audit_error:
            summary = "; ".join(issue.message for issue in report.issues[:6])
            raise ExecutionAuditError("runtime audit verification failed: " + summary)
        return report

    def note_resume(
        self,
        run_id: str,
        *,
        checkpoint_sequence: int,
        expected_audit_head: str,
        expected_audit_events: int,
    ) -> ExecutionAuditCheckpoint:
        checkpoint_sequence = non_negative_int("checkpoint_sequence", checkpoint_sequence)
        expected_audit_head = self._hex_fingerprint(
            "expected_audit_head",
            expected_audit_head,
        )
        expected_audit_events = non_negative_int(
            "expected_audit_events",
            expected_audit_events,
        )
        ledger = self.audit_store.get(run_id)
        if ledger is None:
            if expected_audit_events:
                raise ExecutionAuditError(
                    "checkpoint expects audit events but no ledger exists"
                )
            ledger = self.audit_store.get_or_create(run_id)
        entries = ledger.entries()
        if len(entries) < expected_audit_events:
            raise ExecutionAuditError(
                f"audit ledger is shorter than checkpoint prefix: expected at least {expected_audit_events}, got {len(entries)}"
            )
        prefix_head = (
            GENESIS_HASH
            if expected_audit_events == 0
            else entries[expected_audit_events - 1].event_hash
        )
        if prefix_head != expected_audit_head:
            raise ExecutionAuditError("audit checkpoint prefix head mismatch on resume")
        self.verify_audit(run_id)
        ledger.append(
            AuditEventKind.RUN_RESUMED,
            {
                "checkpoint_sequence": checkpoint_sequence,
                "audit_head": expected_audit_head,
                "audit_events": expected_audit_events,
                "current_audit_head_before_resume": ledger.head_hash,
                "current_audit_events_before_resume": ledger.event_count,
            },
            severity=AuditSeverity.SECURITY,
        )
        return ledger.checkpoint()

    def pending_operations(self, run_id: str | None = None) -> tuple[GuardedToolExecution, ...]:
        with self._lock:
            values = tuple(self._pending.values())
        if run_id is None:
            return values
        run_id = require_id("run_id", run_id)
        return tuple(item for item in values if item.request.run_id == run_id)

    def finalizations(self, run_id: str | None = None) -> tuple[GuardFinalization, ...]:
        with self._lock:
            values = tuple(self._finalized.values())
        if run_id is None:
            return values
        run_id = require_id("run_id", run_id)
        return tuple(item for item in values if item.run_id == run_id)

    def _reserve_operation(self, operation_id: str) -> None:
        operation_id = require_id("operation_id", operation_id)
        with self._lock:
            if (
                operation_id in self._reserved
                or operation_id in self._pending
                or operation_id in self._finalized
            ):
                raise RuntimeGuardDenied(
                    "duplicate or replayed guarded operation",
                    operation_id=operation_id,
                )
            self._reserved.add(operation_id)

    def _decision(
        self,
        request: RuntimeGuardRequest,
        *,
        action: AbstractAction,
        state: CompactState,
        prediction: PredictedTransition,
        profile: RiskGuardProfile,
    ) -> tuple[EpistemicDecision, GuardAdmissionMode]:
        if prediction.observations < profile.minimum_observations:
            if self._cold_start_allowed(request, profile):
                return (
                    self._cold_start_decision(
                        request,
                        action=action,
                        state=state,
                        prediction=prediction,
                        profile=profile,
                    ),
                    GuardAdmissionMode.COLD_START_HOST_TRUST,
                )

        decision_policy = DecisionPolicy(
            maximum_risk=profile.risk,
            minimum_lower_utility=profile.minimum_lower_utility,
            maximum_regret=profile.maximum_regret,
            maximum_model_uncertainty=profile.maximum_model_uncertainty,
            minimum_belief_satisfaction=0.0,
            minimum_verification=profile.minimum_verification,
            observation_margin=0.04,
            abstain_margin=profile.minimum_lower_utility,
            require_stress_survival=profile.require_stress_survival,
            require_nonnegative_joint_adverse=profile.require_nonnegative_joint_adverse,
        )
        candidate = ActionCandidate(
            action=action,
            intrinsic_value=profile.intrinsic_value,
            minimum_observations=max(1, profile.minimum_observations),
            metadata={
                "runtime_guard": True,
                "profile_fingerprint": profile.fingerprint,
                "host_policy_id": request.host_policy_decision.policy_id,
            },
        )
        decision = EpistemicDecisionBridge(
            self.world,
            self.transition_model,
            policy=decision_policy,
        ).decide(state.state_id, (candidate,))
        return decision, GuardAdmissionMode.MODEL_GATED

    def _cold_start_allowed(
        self,
        request: RuntimeGuardRequest,
        profile: RiskGuardProfile,
    ) -> bool:
        if not profile.allow_cold_start:
            return False
        if not profile.cold_start_requires_confirmation:
            return True
        confirmation_id = f"confirm:{request.tool_spec.name}:{request.run_id}"
        return confirmation_id in request.confirmed_actions

    def _cold_start_decision(
        self,
        request: RuntimeGuardRequest,
        *,
        action: AbstractAction,
        state: CompactState,
        prediction: PredictedTransition,
        profile: RiskGuardProfile,
    ) -> EpistemicDecision:
        world_fingerprint = self.world.snapshot(persist=False).fingerprint
        model_fingerprint = self.transition_model.fingerprint
        policy_fingerprint = stable_fingerprint(
            {
                "runtime_guard_policy": self.policy.fingerprint,
                "profile": profile.fingerprint,
                "mode": GuardAdmissionMode.COLD_START_HOST_TRUST.value,
                "host_policy": {
                    "policy_id": request.host_policy_decision.policy_id,
                    "decision": request.host_policy_decision.decision.value,
                    "risk": request.host_policy_decision.risk.value
                    if request.host_policy_decision.risk
                    else None,
                },
            }
        )
        reasons = (
            "transition_model_below_minimum_observations",
            "cold_start_explicitly_allowed_by_runtime_guard_profile",
            "host_execution_policy_already_allowed_call",
        )
        if profile.cold_start_requires_confirmation:
            reasons += ("exact_runtime_confirmation_present",)
        fingerprint = stable_fingerprint(
            {
                "state": state.state_id,
                "action": action.action_id,
                "intent": action.metadata.get("tool_intent_fingerprint"),
                "mode": GuardAdmissionMode.COLD_START_HOST_TRUST.value,
                "prediction": self._prediction_fingerprint(prediction),
                "world": world_fingerprint,
                "model": model_fingerprint,
                "policy": policy_fingerprint,
                "reasons": reasons,
            }
        )
        return EpistemicDecision(
            decision_id=stable_id("epistemic_decision", {"fingerprint": fingerprint}),
            disposition=DecisionDisposition.ACT,
            selected_action=action,
            selected_observation=None,
            assessments=(),
            regret=(),
            reasons=reasons,
            world_fingerprint=world_fingerprint,
            model_fingerprint=model_fingerprint,
            policy_fingerprint=policy_fingerprint,
            fingerprint=fingerprint,
        )

    def _compact_state(
        self,
        request: RuntimeGuardRequest,
        *,
        phase: str,
        signals: RuntimeGuardSignals | None = None,
        extra_features: Mapping[str, Any] | None = None,
    ) -> CompactState:
        selected = signals or request.signals
        features: dict[str, Any] = {
            "phase": phase,
            "goal": request.goal_id,
            "tool": request.call.name,
            "step": request.step_id,
            "plan_version": request.plan_version,
            "attempt": request.attempt,
            "risk": request.tool_spec.risk.value,
        }
        features.update(dict(extra_features or {}))
        return CompactState.from_signals(
            features=features,
            progress=selected.progress,
            uncertainty=selected.uncertainty,
            budget_pressure=selected.budget_pressure,
            failure_pressure=selected.failure_pressure,
            risk=request.tool_spec.risk,
            terminal=selected.terminal,
            metadata={
                "run_id": request.run_id,
                "request_fingerprint": self._request_fingerprint(request),
            },
        )

    def _audit(
        self,
        ledger,
        kind: AuditEventKind,
        operation_id: str,
        payload: Mapping[str, Any],
        *,
        severity: AuditSeverity = AuditSeverity.INFO,
    ) -> None:
        try:
            ledger.append(
                kind,
                payload,
                operation_id=operation_id,
                severity=severity,
            )
        except Exception:
            if self.policy.fail_closed_on_audit_error:
                raise

    @staticmethod
    def _reward(outcome: TransitionOutcome, verification_score: float) -> float:
        base = {
            TransitionOutcome.SUCCESS: 0.70,
            TransitionOutcome.FAILURE: -0.70,
            TransitionOutcome.BLOCKED: -0.40,
            TransitionOutcome.INTERRUPTED: -0.25,
            TransitionOutcome.UNKNOWN: -0.10,
        }[outcome]
        verification_adjustment = (verification_score - 0.5) * 0.60
        return max(-1.0, min(1.0, base + verification_adjustment))

    @staticmethod
    def _most_likely_next(prediction: PredictedTransition) -> str | None:
        if not prediction.next_state_probabilities:
            return None
        return max(
            prediction.next_state_probabilities.items(),
            key=lambda item: (item[1], item[0]),
        )[0]

    @staticmethod
    def _observation_fingerprint(observation: ToolObservation) -> str:
        return stable_fingerprint(
            {
                "call_id": observation.call_id,
                "tool_name": observation.tool_name,
                "ok": observation.ok,
                "payload": observation.payload,
                "error": observation.error,
                "evidence": [
                    (
                        ref.evidence_id,
                        ref.kind.value,
                        ref.source,
                        ref.fingerprint,
                        ref.confidence,
                        ref.observed_at,
                    )
                    for ref in observation.evidence
                ],
                "cached": observation.cached,
            }
        )

    @staticmethod
    def _prediction_fingerprint(prediction: PredictedTransition) -> str:
        return stable_fingerprint(
            {
                "state": prediction.state_id,
                "action": prediction.action_id,
                "next": sorted(prediction.next_state_probabilities.items()),
                "outcomes": sorted(prediction.outcome_probabilities.items()),
                "reward": prediction.expected_reward,
                "verification": prediction.expected_verification,
                "cost": prediction.expected_cost,
                "latency": prediction.expected_latency_ms,
                "uncertainty": prediction.uncertainty,
                "observations": prediction.observations,
            }
        )

    @staticmethod
    def _request_fingerprint(request: RuntimeGuardRequest) -> str:
        return stable_fingerprint(
            {
                "run_id": request.run_id,
                "goal_id": request.goal_id,
                "step_id": request.step_id,
                "attempt": request.attempt,
                "plan_version": request.plan_version,
                "call": {
                    "id": request.call.call_id,
                    "name": request.call.name,
                    "arguments": request.call.arguments,
                },
                "context": {
                    "run_id": request.execution_context.run_id,
                    "user_id": request.execution_context.user_id,
                    "trace_id": request.execution_context.trace_id,
                },
                "tool": {
                    "name": request.tool_spec.name,
                    "risk": request.tool_spec.risk.value,
                    "timeout": request.tool_spec.timeout_seconds,
                },
                "host_policy": {
                    "decision": request.host_policy_decision.decision.value,
                    "reason": request.host_policy_decision.reason,
                    "policy_id": request.host_policy_decision.policy_id,
                    "risk": request.host_policy_decision.risk.value
                    if request.host_policy_decision.risk
                    else None,
                },
                "confirmed": request.confirmed_actions,
                "usage": {
                    "steps": request.usage.steps,
                    "model_calls": request.usage.model_calls,
                    "tool_calls": request.usage.tool_calls,
                    "tokens": request.usage.total_tokens,
                },
                "signals": {
                    "progress": request.signals.progress,
                    "uncertainty": request.signals.uncertainty,
                    "budget_pressure": request.signals.budget_pressure,
                    "failure_pressure": request.signals.failure_pressure,
                    "terminal": request.signals.terminal,
                },
                "evidence_ids": request.evidence_ids,
                "metadata": request.metadata,
            }
        )

    @staticmethod
    def _hex_fingerprint(name: str, value: str) -> str:
        normalized = str(value).strip().lower()
        if len(normalized) != 64 or any(ch not in "0123456789abcdef" for ch in normalized):
            raise AgentContractError(f"{name} must be sha256 hex")
        return normalized