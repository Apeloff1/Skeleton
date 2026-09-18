"""Resumable evidence-first execution runtime for Jeeves.

The runtime is the deterministic control plane around probabilistic model calls.
It owns state transitions, budgets, checkpoints, tool authorization, evidence
custody, verification, replanning, final grounding, memory staging, telemetry,
and cancellation.  Models propose plans/analysis/answers; they never directly
mutate durable state or decide that an external action succeeded.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Mapping, Sequence

from .cognition import (
    ContextCompiler,
    ContextSection,
    FINAL_RESPONSE_SCHEMA,
    FinalDraft,
    FinalDraftDecoder,
    PromptCompiler,
    RunScratchpad,
)
from .fabric_cognition import FabricContextCompiler
from .evidence import (
    EvidenceArtifact,
    EvidenceLedger,
    GroundingGate,
    GroundingPolicy,
    GroundingReport,
    LearningEvidenceBridge,
)
from .memory import MemoryError, MemoryManager, MemoryNamespace
from .planning import (
    ModelPlanParser,
    PLAN_SCHEMA,
    PlanScheduler,
    PlanValidator,
    ReplanPolicy,
    retain_completed_steps,
)
from .policy import ExecutionPolicy, PolicyContext
from .provider import ProviderExhausted, ProviderRouter, ProviderUnavailable
from .telemetry import MetricsRegistry, TraceLedger, Tracer
from .tools import ToolExecutionContext, ToolExecutor, ToolGrant, ToolRegistry
from .types import (
    AgentContractError,
    AgentPhase,
    AgentResult,
    Budget,
    Claim,
    Decision,
    EvidenceRef,
    Goal,
    MemoryKind,
    ModelRequest,
    ModelResponse,
    Plan,
    PlanStep,
    RiskTier,
    StepStatus,
    TerminationReason,
    ToolCall,
    ToolObservation,
    Usage,
    json_safe,
    positive_int,
    probability,
    require_id,
    stable_fingerprint,
    stable_id,
    usage_from_response,
)
from .verification import (
    StepVerifier,
    VerificationPolicy,
    VerificationReport,
    parse_advisory_json,
)


class RuntimeErrorBase(RuntimeError):
    pass


class RunCancelled(RuntimeErrorBase):
    pass


class BudgetExhausted(RuntimeErrorBase):
    def __init__(self, reason: TerminationReason, message: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class AgentConfig:
    planner_max_tokens: int = 4_096
    step_max_tokens: int = 3_072
    verifier_max_tokens: int = 1_024
    final_max_tokens: int = 4_096
    model_temperature: float = 0.0
    maximum_plan_steps: int = 32
    maximum_replans: int = 2
    grounding_repairs: int = 1
    enable_model_verification: bool = True
    verify_read_only_with_model: bool = False
    stage_memory_candidates: bool = True
    stage_success_episode: bool = True
    bridge_verified_evidence: bool = False
    fail_on_unresolved: bool = False
    minimum_final_confidence: float = 0.5
    working_memory_ttl_seconds: float = 24 * 3600.0

    def __post_init__(self) -> None:
        for name in (
            "planner_max_tokens",
            "step_max_tokens",
            "verifier_max_tokens",
            "final_max_tokens",
            "maximum_plan_steps",
        ):
            object.__setattr__(self, name, positive_int(name, getattr(self, name), maximum=1_000_000))
        if isinstance(self.maximum_replans, bool) or not isinstance(self.maximum_replans, int) or self.maximum_replans < 0:
            raise AgentContractError("maximum_replans must be a non-negative integer")
        if isinstance(self.grounding_repairs, bool) or not isinstance(self.grounding_repairs, int) or self.grounding_repairs < 0:
            raise AgentContractError("grounding_repairs must be a non-negative integer")
        temperature = float(self.model_temperature)
        if not 0.0 <= temperature <= 2.0:
            raise AgentContractError("model_temperature must be in [0, 2]")
        object.__setattr__(self, "model_temperature", temperature)
        object.__setattr__(
            self,
            "minimum_final_confidence",
            probability("minimum_final_confidence", self.minimum_final_confidence),
        )
        ttl = float(self.working_memory_ttl_seconds)
        if ttl <= 0:
            raise AgentContractError("working_memory_ttl_seconds must be positive")
        object.__setattr__(self, "working_memory_ttl_seconds", ttl)


@dataclass(frozen=True, slots=True)
class RunInputs:
    goal: Goal
    tenant_id: str
    user_id: str
    workspace_id: str = "default"
    session_id: str | None = None
    run_id: str | None = None
    budget: Budget = field(default_factory=Budget)
    grants: tuple[ToolGrant, ...] = ()
    confirmed_actions: tuple[str, ...] = ()
    preferred_provider: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.goal, Goal):
            raise AgentContractError("goal must be Goal")
        object.__setattr__(self, "tenant_id", require_id("tenant_id", self.tenant_id))
        object.__setattr__(self, "user_id", require_id("user_id", self.user_id))
        object.__setattr__(self, "workspace_id", require_id("workspace_id", self.workspace_id))
        if self.session_id is not None:
            object.__setattr__(self, "session_id", require_id("session_id", self.session_id))
        if self.run_id is not None:
            object.__setattr__(self, "run_id", require_id("run_id", self.run_id))
        if not isinstance(self.budget, Budget):
            raise AgentContractError("budget must be Budget")
        grants = tuple(self.grants)
        if any(not isinstance(grant, ToolGrant) for grant in grants):
            raise AgentContractError("grants must contain ToolGrant values")
        object.__setattr__(self, "grants", grants)
        object.__setattr__(
            self,
            "confirmed_actions",
            tuple(require_id("confirmed_action", item) for item in self.confirmed_actions),
        )
        if self.preferred_provider is not None:
            object.__setattr__(self, "preferred_provider", require_id("preferred_provider", self.preferred_provider))
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def namespace(self) -> MemoryNamespace:
        return MemoryNamespace(
            tenant_id=self.tenant_id,
            user_id=self.user_id,
            workspace_id=self.workspace_id,
            session_id=self.session_id,
        )


@dataclass(frozen=True, slots=True)
class RunCheckpoint:
    run_id: str
    goal_id: str
    phase: AgentPhase
    sequence: int
    usage: Usage
    plan: Plan | None = None
    observations: tuple[ToolObservation, ...] = ()
    evidence: tuple[EvidenceArtifact, ...] = ()
    scratch: Mapping[str, Any] = field(default_factory=dict)
    replan_count: int = 0
    previous_trace_fingerprint: str = ""
    current_trace_fingerprint: str = ""
    last_error: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", require_id("run_id", self.run_id))
        object.__setattr__(self, "goal_id", require_id("goal_id", self.goal_id))
        if not isinstance(self.phase, AgentPhase):
            object.__setattr__(self, "phase", AgentPhase(str(self.phase)))
        object.__setattr__(self, "sequence", positive_int("sequence", self.sequence, maximum=10_000_000))
        if not isinstance(self.usage, Usage):
            raise AgentContractError("checkpoint usage must be Usage")
        if self.plan is not None and not isinstance(self.plan, Plan):
            raise AgentContractError("checkpoint plan must be Plan or None")
        observations = tuple(self.observations)
        if any(not isinstance(item, ToolObservation) for item in observations):
            raise AgentContractError("checkpoint observations must contain ToolObservation")
        object.__setattr__(self, "observations", observations)
        artifacts = tuple(self.evidence)
        if any(not isinstance(item, EvidenceArtifact) for item in artifacts):
            raise AgentContractError("checkpoint evidence must contain EvidenceArtifact")
        object.__setattr__(self, "evidence", artifacts)
        object.__setattr__(self, "scratch", json_safe(dict(self.scratch)))
        if isinstance(self.replan_count, bool) or not isinstance(self.replan_count, int) or self.replan_count < 0:
            raise AgentContractError("replan_count must be a non-negative integer")
        for name in ("previous_trace_fingerprint", "current_trace_fingerprint"):
            value = getattr(self, name)
            if value:
                normalized = str(value).strip().lower()
                if len(normalized) < 32:
                    raise AgentContractError(f"{name} is invalid")
                object.__setattr__(self, name, normalized)
        if self.last_error is not None:
            object.__setattr__(self, "last_error", str(self.last_error)[:8192])
        if self.updated_at < self.created_at:
            raise AgentContractError("checkpoint updated_at predates created_at")
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "goal_id": self.goal_id,
            "phase": self.phase.value,
            "sequence": self.sequence,
            "usage": {
                "steps": self.usage.steps,
                "model_calls": self.usage.model_calls,
                "tool_calls": self.usage.tool_calls,
                "prompt_tokens": self.usage.prompt_tokens,
                "completion_tokens": self.usage.completion_tokens,
                "cached_model_calls": self.usage.cached_model_calls,
            },
            "plan": self.plan.to_dict() if self.plan is not None else None,
            "observations": [
                {
                    "call_id": item.call_id,
                    "tool_name": item.tool_name,
                    "ok": item.ok,
                    "payload": item.payload,
                    "error": item.error,
                    "evidence": [ref.evidence_id for ref in item.evidence],
                    "latency_ms": item.latency_ms,
                    "cached": item.cached,
                }
                for item in self.observations
            ],
            "evidence": [
                {
                    "evidence_id": item.evidence_id,
                    "fingerprint": item.fingerprint,
                    "kind": item.kind.value,
                    "source": item.source,
                    "observed_at": item.observed_at,
                }
                for item in self.evidence
            ],
            "scratch": dict(self.scratch),
            "replan_count": self.replan_count,
            "previous_trace_fingerprint": self.previous_trace_fingerprint,
            "current_trace_fingerprint": self.current_trace_fingerprint,
            "last_error": self.last_error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": dict(self.metadata),
        }


class InMemoryCheckpointer:
    """Thread-safe checkpoint history with bounded per-run retention."""

    def __init__(self, *, max_versions_per_run: int = 64) -> None:
        self.max_versions_per_run = positive_int(
            "max_versions_per_run",
            max_versions_per_run,
            maximum=10_000,
        )
        self._history: dict[str, list[RunCheckpoint]] = {}
        self._lock = threading.RLock()

    def save(self, checkpoint: RunCheckpoint) -> RunCheckpoint:
        if not isinstance(checkpoint, RunCheckpoint):
            raise TypeError("checkpoint must be RunCheckpoint")
        with self._lock:
            history = self._history.setdefault(checkpoint.run_id, [])
            if history and checkpoint.sequence <= history[-1].sequence:
                raise RuntimeErrorBase("checkpoint sequence must increase monotonically")
            history.append(checkpoint)
            overflow = len(history) - self.max_versions_per_run
            if overflow > 0:
                del history[:overflow]
        return checkpoint

    def latest(self, run_id: str) -> RunCheckpoint | None:
        run_id = require_id("run_id", run_id)
        with self._lock:
            history = self._history.get(run_id, [])
            return history[-1] if history else None

    def history(self, run_id: str) -> tuple[RunCheckpoint, ...]:
        run_id = require_id("run_id", run_id)
        with self._lock:
            return tuple(self._history.get(run_id, ()))

    def clear(self, run_id: str) -> bool:
        run_id = require_id("run_id", run_id)
        with self._lock:
            return self._history.pop(run_id, None) is not None

    def runs(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._history))


@dataclass(slots=True)
class _RunState:
    run_id: str
    inputs: RunInputs
    phase: AgentPhase
    usage: Usage
    plan: Plan | None
    observations: list[ToolObservation]
    ledger: EvidenceLedger
    scratch: RunScratchpad
    trace: TraceLedger
    tracer: Tracer
    started_monotonic: float
    created_wall: float
    replan_count: int = 0
    checkpoint_sequence: int = 0
    previous_trace_fingerprint: str = ""
    last_error: str | None = None
    last_verification: VerificationReport | None = None


class JeevesAgentRuntime:
    """Deterministic host runtime around provider-backed Jeeves reasoning."""

    def __init__(
        self,
        *,
        provider_router: ProviderRouter,
        tool_registry: ToolRegistry | None = None,
        tool_executor: ToolExecutor | None = None,
        memory: MemoryManager | None = None,
        checkpointer: InMemoryCheckpointer | None = None,
        execution_policy: ExecutionPolicy | None = None,
        grounding_policy: GroundingPolicy | None = None,
        verification_policy: VerificationPolicy | None = None,
        context_compiler: ContextCompiler | None = None,
        prompt_compiler: PromptCompiler | None = None,
        config: AgentConfig | None = None,
        metrics: MetricsRegistry | None = None,
        learning_bridge: LearningEvidenceBridge | None = None,
        wall_clock: Callable[[], float] = time.time,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if not isinstance(provider_router, ProviderRouter):
            raise TypeError("provider_router must be ProviderRouter")
        self.providers = provider_router
        self.tools = tool_registry or ToolRegistry()
        self._wall_clock = wall_clock
        self._monotonic = monotonic
        self.tool_executor = tool_executor or ToolExecutor(
            self.tools,
            clock=wall_clock,
            monotonic=monotonic,
        )
        self.memory = memory or MemoryManager(clock=wall_clock)
        self.checkpointer = checkpointer or InMemoryCheckpointer()
        self.execution_policy = execution_policy or ExecutionPolicy(
            clock=wall_clock,
            monotonic=monotonic,
        )
        self.grounding_policy = grounding_policy or GroundingPolicy()
        self.verification_policy = verification_policy or VerificationPolicy()
        self.context = context_compiler or FabricContextCompiler()
        self.prompts = prompt_compiler or PromptCompiler()
        self.config = config or AgentConfig()
        self.metrics = metrics or MetricsRegistry()
        self.learning_bridge = learning_bridge
        self.scheduler = PlanScheduler()
        self.plan_parser = ModelPlanParser(maximum_steps=self.config.maximum_plan_steps)
        self.plan_validator = PlanValidator(maximum_steps=self.config.maximum_plan_steps)
        self.replan_policy = ReplanPolicy(max_plan_versions=self.config.maximum_replans + 1)
        self._cancelled: set[str] = set()
        self._cancel_lock = threading.RLock()

    def run(self, inputs: RunInputs) -> AgentResult:
        """Start and synchronously complete one bounded agent run."""
        if not isinstance(inputs, RunInputs):
            raise TypeError("inputs must be RunInputs")
        run_id = inputs.run_id or stable_id(
            "run",
            {
                "goal": inputs.goal.goal_id,
                "tenant": inputs.tenant_id,
                "user": inputs.user_id,
                "session": inputs.session_id,
                "at": self._wall_clock(),
            },
        )
        if self.checkpointer.latest(run_id) is not None:
            raise RuntimeErrorBase(f"run already exists: {run_id}")
        state = self._new_state(run_id, inputs)
        return self._drive(state)

    def resume(self, inputs: RunInputs, run_id: str) -> AgentResult:
        """Resume from the latest retained checkpoint without repeating succeeded steps."""
        run_id = require_id("run_id", run_id)
        checkpoint = self.checkpointer.latest(run_id)
        if checkpoint is None:
            raise RuntimeErrorBase(f"no checkpoint for run: {run_id}")
        if checkpoint.goal_id != inputs.goal.goal_id:
            raise RuntimeErrorBase("resume goal does not match checkpoint")
        if checkpoint.phase in {AgentPhase.COMPLETED, AgentPhase.CANCELLED}:
            raise RuntimeErrorBase("cannot resume a terminal run")
        state = self._state_from_checkpoint(inputs, checkpoint)
        return self._drive(state)

    def cancel(self, run_id: str) -> None:
        run_id = require_id("run_id", run_id)
        with self._cancel_lock:
            self._cancelled.add(run_id)

    def clear_cancel(self, run_id: str) -> None:
        run_id = require_id("run_id", run_id)
        with self._cancel_lock:
            self._cancelled.discard(run_id)

    def _cancel_requested(self, run_id: str) -> bool:
        with self._cancel_lock:
            return run_id in self._cancelled

    def _new_state(self, run_id: str, inputs: RunInputs) -> _RunState:
        trace = TraceLedger(
            trace_id=stable_id("trace", {"run": run_id, "segment": 1}),
            run_id=run_id,
            clock=self._wall_clock,
        )
        ledger = EvidenceLedger(clock=self._wall_clock)
        state = _RunState(
            run_id=run_id,
            inputs=inputs,
            phase=AgentPhase.CREATED,
            usage=Usage(),
            plan=None,
            observations=[],
            ledger=ledger,
            scratch=RunScratchpad(),
            trace=trace,
            tracer=Tracer(trace, monotonic=self._monotonic),
            started_monotonic=self._monotonic(),
            created_wall=self._wall_clock(),
        )
        trace.emit(
            "run.created",
            {
                "goal_id": inputs.goal.goal_id,
                "tenant_id": inputs.tenant_id,
                "user_id": inputs.user_id,
                "workspace_id": inputs.workspace_id,
                "session_id": inputs.session_id,
                "budget": self._budget_dict(inputs.budget),
            },
        )
        self._remember_working(
            inputs.namespace,
            inputs.goal.objective,
            source="run-goal",
            tags=("goal", run_id),
            trust=1.0,
            salience=0.9,
        )
        self._checkpoint(state)
        return state

    def _state_from_checkpoint(self, inputs: RunInputs, checkpoint: RunCheckpoint) -> _RunState:
        segment = len(self.checkpointer.history(checkpoint.run_id)) + 1
        trace = TraceLedger(
            trace_id=stable_id("trace", {"run": checkpoint.run_id, "segment": segment}),
            run_id=checkpoint.run_id,
            clock=self._wall_clock,
        )
        trace.emit(
            "run.resumed",
            {
                "checkpoint_sequence": checkpoint.sequence,
                "previous_trace_fingerprint": checkpoint.current_trace_fingerprint,
                "phase": checkpoint.phase.value,
            },
        )
        ledger = EvidenceLedger(clock=self._wall_clock)
        for artifact in checkpoint.evidence:
            ledger.append(artifact)
        scratch = RunScratchpad()
        for key, raw in checkpoint.scratch.items():
            if isinstance(raw, dict) and "value" in raw:
                scratch.set(key, raw["value"], importance=float(raw.get("importance", 0.5)))
            else:
                scratch.set(key, raw)
        # A process may have died while a step was RUNNING.  It is unsafe to
        # repeat a mutating step automatically, so mark it failed; the replan
        # path can inspect existing observations/evidence before deciding next.
        plan = checkpoint.plan
        if plan is not None:
            for step in tuple(plan.steps):
                if step.status is StepStatus.RUNNING:
                    recovered = step.with_status(StepStatus.FAILED)
                    plan = plan.replace_step(recovered)
        return _RunState(
            run_id=checkpoint.run_id,
            inputs=inputs,
            phase=checkpoint.phase,
            usage=checkpoint.usage,
            plan=plan,
            observations=list(checkpoint.observations),
            ledger=ledger,
            scratch=scratch,
            trace=trace,
            tracer=Tracer(trace, monotonic=self._monotonic),
            started_monotonic=self._monotonic(),
            created_wall=checkpoint.created_at,
            replan_count=checkpoint.replan_count,
            checkpoint_sequence=checkpoint.sequence,
            previous_trace_fingerprint=checkpoint.current_trace_fingerprint,
            last_error=checkpoint.last_error,
        )

    def _drive(self, state: _RunState) -> AgentResult:
        try:
            if state.phase is AgentPhase.CREATED or state.plan is None:
                self._transition(state, AgentPhase.PLANNING)
                self._plan(state)
            while True:
                self._raise_if_cancelled(state)
                self._raise_if_budget_exhausted(state)
                if state.plan is None:
                    return self._finish_failure(state, TerminationReason.PLAN_INVALID, "No valid plan was produced.")
                state.plan = self.scheduler.normalize(state.plan)
                if state.plan.complete:
                    break
                ready = state.plan.ready_steps()
                if not ready:
                    if state.plan.failed:
                        if self._attempt_replan(state, "plan contains failed or blocked steps"):
                            continue
                        return self._finish_failure(
                            state,
                            TerminationReason.VERIFICATION_FAILED,
                            "The plan could not continue after a failed dependency.",
                        )
                    return self._finish_failure(
                        state,
                        TerminationReason.PLAN_INVALID,
                        "The plan has no executable step and is not complete.",
                    )
                step = ready[0]
                result = self._execute_step(state, step)
                if result is not None:
                    return result
            self._transition(state, AgentPhase.FINALIZING)
            return self._finalize(state)
        except RunCancelled:
            return self._finish_failure(state, TerminationReason.CANCELLED, "Run cancelled by caller.", cancelled=True)
        except BudgetExhausted as exc:
            return self._finish_failure(state, exc.reason, str(exc))
        except (ProviderUnavailable, ProviderExhausted) as exc:
            return self._finish_failure(state, TerminationReason.PROVIDER_UNAVAILABLE, str(exc))
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as exc:
            state.last_error = f"{type(exc).__name__}: {str(exc)[:4000]}"
            state.trace.emit("run.internal_error", {"error": state.last_error})
            return self._finish_failure(
                state,
                TerminationReason.INTERNAL_ERROR,
                "Jeeves encountered an internal runtime error.",
                metadata={"error_type": type(exc).__name__},
            )
        finally:
            self.metrics.increment("agent.runs.finished")

    def _plan(self, state: _RunState) -> None:
        with state.tracer.span("agent.plan", goal_id=state.inputs.goal.goal_id):
            packet = self.context.compile(
                system_instruction=self.prompts.system(mode="planner"),
                task_instruction=self.prompts.planning_task(
                    available_tools=[spec.name for spec in self.tools.specs()]
                ),
                goal=state.inputs.goal,
                namespace=state.inputs.namespace,
                memory=self.memory,
                evidence=state.ledger,
                observations=state.observations,
                scratchpad=state.scratch,
            )
            response = self._model_call(
                state,
                messages=packet.messages(),
                requested_max_tokens=self.config.planner_max_tokens,
                tools=self.tools.model_schemas(),
                response_schema=PLAN_SCHEMA,
                metadata={"purpose": "planning", "context": packet.fingerprint},
            )
            plan = self.plan_parser.parse(state.inputs.goal, response.content)
            report = self.plan_validator.validate(
                plan,
                available_tools={spec.name for spec in self.tools.specs()},
            )
            if not report.valid:
                state.trace.emit(
                    "plan.rejected",
                    {"errors": list(report.errors), "warnings": list(report.warnings)},
                )
                raise RuntimeErrorBase("invalid model plan: " + "; ".join(report.errors))
            state.plan = self.scheduler.normalize(plan)
            state.trace.emit(
                "plan.accepted",
                {
                    "plan_id": plan.plan_id,
                    "version": plan.version,
                    "steps": len(plan.steps),
                    "critical_path": list(report.critical_path),
                },
            )
            self.metrics.increment("agent.plans.accepted")
            self._checkpoint(state)

    def _execute_step(self, state: _RunState, step: PlanStep) -> AgentResult | None:
        self._transition(state, AgentPhase.EXECUTING)
        assert state.plan is not None
        state.plan = self.scheduler.start(state.plan, step.step_id)
        step = state.plan.step(step.step_id)
        state.usage = state.usage.add(steps=1)
        state.trace.emit(
            "step.started",
            {
                "step_id": step.step_id,
                "tool": step.tool,
                "risk": step.risk.value,
                "attempt": step.attempts,
            },
        )
        self._checkpoint(state)

        if step.tool is None:
            return self._execute_reasoning_step(state, step)
        return self._execute_tool_step(state, step)

    def _execute_reasoning_step(self, state: _RunState, step: PlanStep) -> AgentResult | None:
        packet = self.context.compile(
            system_instruction=self.prompts.system(mode="reasoning-step"),
            task_instruction=self.prompts.reasoning_step_task(step),
            goal=state.inputs.goal,
            namespace=state.inputs.namespace,
            memory=self.memory,
            evidence=state.ledger,
            plan=state.plan,
            current_step=step,
            observations=state.observations,
            scratchpad=state.scratch,
        )
        response = self._model_call(
            state,
            messages=packet.messages(),
            requested_max_tokens=self.config.step_max_tokens,
            metadata={"purpose": "reasoning-step", "step_id": step.step_id, "context": packet.fingerprint},
        )
        state.scratch.set(f"analysis:{step.step_id}", response.content, importance=0.7)
        self._remember_working(
            state.inputs.namespace,
            response.content,
            source="model-analysis",
            tags=("analysis", step.step_id, state.run_id),
            trust=0.35,
            salience=0.45,
        )
        verifier = StepVerifier(state.ledger, policy=self.verification_policy, clock=self._wall_clock)
        self._transition(state, AgentPhase.VERIFYING)
        report = verifier.verify(step)
        state.last_verification = report
        if report.passed:
            assert state.plan is not None
            state.plan = self.scheduler.succeed(state.plan, step.step_id)
            state.trace.emit("step.succeeded", self._verification_event(report))
            self._checkpoint(state)
            return None
        return self._handle_step_failure(state, step, report, tool_failed=False)

    def _execute_tool_step(self, state: _RunState, step: PlanStep) -> AgentResult | None:
        registered = self.tools.get(step.tool or "")
        if registered is None:
            assert state.plan is not None
            state.plan = self.scheduler.fail(state.plan, step.step_id, retryable=False)
            state.last_error = f"tool unavailable: {step.tool}"
            return self._handle_step_failure(state, step, None, tool_failed=True)

        context = PolicyContext(
            run_id=state.run_id,
            user_id=state.inputs.user_id,
            goal=state.inputs.goal,
            usage=state.usage,
            budget=state.inputs.budget,
            started_at=state.started_monotonic,
            confirmed_actions=state.inputs.confirmed_actions,
            metadata=state.inputs.metadata,
        )
        decision = self.execution_policy.check_tool(
            context,
            registered.spec,
            step.arguments,
            state.inputs.grants,
        )
        state.trace.emit(
            "tool.policy",
            {
                "step_id": step.step_id,
                "tool": step.tool,
                "decision": decision.decision.value,
                "reason": decision.reason,
                "confirmation_id": decision.required_confirmation_id,
            },
        )
        if decision.decision is Decision.REQUIRE_CONFIRMATION:
            return self._finish_failure(
                state,
                TerminationReason.CONFIRMATION_REQUIRED,
                decision.reason,
                metadata={"confirmation_id": decision.required_confirmation_id},
                terminal_phase=AgentPhase.FAILED,
            )
        if decision.decision is not Decision.ALLOW:
            assert state.plan is not None
            state.plan = self.scheduler.fail(state.plan, step.step_id, retryable=False)
            return self._finish_failure(
                state,
                TerminationReason.POLICY_DENIED,
                decision.reason,
                metadata={"tool": step.tool, "step_id": step.step_id},
            )

        self._raise_if_tool_budget_exhausted(state)
        call = ToolCall(
            call_id=stable_id(
                "call",
                {
                    "run": state.run_id,
                    "step": step.step_id,
                    "attempt": step.attempts,
                    "tool": step.tool,
                    "arguments": step.arguments,
                },
            ),
            name=step.tool or "",
            arguments=step.arguments,
            reason=step.description,
        )
        execution_context = ToolExecutionContext(
            run_id=state.run_id,
            user_id=state.inputs.user_id,
            trace_id=state.trace.trace_id,
            metadata={"goal_id": state.inputs.goal.goal_id, "step_id": step.step_id},
        )
        with state.tracer.span("agent.tool", tool=call.name, step_id=step.step_id):
            observation = self.tool_executor.execute(
                call,
                execution_context,
                grants=state.inputs.grants,
            )
        state.usage = state.usage.add(tool_calls=1)
        state.observations.append(observation)
        state.trace.emit(
            "tool.observed",
            {
                "call_id": call.call_id,
                "tool": call.name,
                "ok": observation.ok,
                "cached": observation.cached,
                "latency_ms": observation.latency_ms,
                "evidence_ids": [ref.evidence_id for ref in observation.evidence],
            },
        )
        artifacts = state.ledger.ingest_observation(observation)
        self._bridge_artifacts(state, artifacts)
        self._checkpoint(state)

        self._transition(state, AgentPhase.VERIFYING)
        advisory = self._verification_advisory(state, step, observation)
        verifier = StepVerifier(state.ledger, policy=self.verification_policy, clock=self._wall_clock)
        report = verifier.verify(step, observations=(observation,), advisory=advisory)
        state.last_verification = report
        if report.passed:
            assert state.plan is not None
            state.plan = self.scheduler.succeed(state.plan, step.step_id)
            state.trace.emit("step.succeeded", self._verification_event(report))
            self.metrics.increment("agent.steps.succeeded")
            self._checkpoint(state)
            return None

        assert state.plan is not None
        retryable = observation.ok and step.attempts < step.max_attempts and not report.fatal
        state.plan = self.scheduler.fail(state.plan, step.step_id, retryable=retryable)
        state.trace.emit("step.verification_failed", self._verification_event(report))
        self.metrics.increment("agent.steps.verification_failed")
        self._checkpoint(state)
        if retryable:
            return None
        return self._handle_step_failure(state, step, report, tool_failed=not observation.ok)

    def _verification_advisory(
        self,
        state: _RunState,
        step: PlanStep,
        observation: ToolObservation,
    ) -> Mapping[str, Any] | None:
        if not self.config.enable_model_verification:
            return None
        if step.risk is RiskTier.READ_ONLY and not self.config.verify_read_only_with_model:
            return None
        packet = self.context.compile(
            system_instruction=self.prompts.system(mode="verifier"),
            task_instruction=self.prompts.verification_task(step),
            goal=state.inputs.goal,
            namespace=state.inputs.namespace,
            memory=self.memory,
            evidence=state.ledger,
            plan=state.plan,
            current_step=step,
            observations=(observation,),
            scratchpad=state.scratch,
        )
        response = self._model_call(
            state,
            messages=packet.messages(),
            requested_max_tokens=self.config.verifier_max_tokens,
            response_schema={
                "type": "object",
                "required": ["passed", "confidence", "reasons", "evidence_ids"],
                "properties": {
                    "passed": {"type": "boolean"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "reasons": {"type": "array", "items": {"type": "string"}},
                    "evidence_ids": {"type": "array", "items": {"type": "string"}},
                },
            },
            metadata={"purpose": "verification", "step_id": step.step_id, "context": packet.fingerprint},
        )
        try:
            return parse_advisory_json(response.content)
        except Exception as exc:
            state.trace.emit(
                "verification.advisory_rejected",
                {"step_id": step.step_id, "error": f"{type(exc).__name__}: {str(exc)[:512]}"},
            )
            return None

    def _handle_step_failure(
        self,
        state: _RunState,
        step: PlanStep,
        report: VerificationReport | None,
        *,
        tool_failed: bool,
    ) -> AgentResult | None:
        reason = "step execution failed"
        if report is not None:
            reason = "; ".join(check.message for check in report.failures[:8]) or reason
        state.last_error = reason[:8192]
        if self._attempt_replan(state, reason, failed_step_id=step.step_id, tool_failed=tool_failed):
            return None
        termination = TerminationReason.TOOL_FAILURE if tool_failed else TerminationReason.VERIFICATION_FAILED
        return self._finish_failure(state, termination, reason, metadata={"step_id": step.step_id})

    def _attempt_replan(
        self,
        state: _RunState,
        failure_reason: str,
        *,
        failed_step_id: str | None = None,
        tool_failed: bool = False,
    ) -> bool:
        if state.plan is None or state.replan_count >= self.config.maximum_replans:
            return False
        decision = self.replan_policy.decide(
            state.plan,
            failed_step_id=failed_step_id,
            tool_failed=tool_failed,
            evidence_conflict=bool(
                state.last_verification and state.last_verification.contradictions
            ),
        )
        if not decision.should_replan:
            return False
        self._transition(state, AgentPhase.REPLANNING)
        state.replan_count += 1
        extra = ContextSection(
            "replan_failure",
            json_safe({
                "reason": failure_reason,
                "failed_step_id": failed_step_id,
                "last_verification": self._verification_event(state.last_verification) if state.last_verification else None,
            }).__repr__(),
            priority=100,
            required=True,
        )
        packet = self.context.compile(
            system_instruction=self.prompts.system(mode="replanner"),
            task_instruction=self.prompts.replan_task(failure_reason=failure_reason),
            goal=state.inputs.goal,
            namespace=state.inputs.namespace,
            memory=self.memory,
            evidence=state.ledger,
            plan=state.plan,
            observations=state.observations,
            scratchpad=state.scratch,
            extra_sections=(extra,),
        )
        response = self._model_call(
            state,
            messages=packet.messages(),
            requested_max_tokens=self.config.planner_max_tokens,
            tools=self.tools.model_schemas(),
            response_schema=PLAN_SCHEMA,
            metadata={"purpose": "replanning", "context": packet.fingerprint, "version": state.plan.version},
        )
        proposed = self.plan_parser.parse(state.inputs.goal, response.content)
        proposed = replace(proposed, version=state.plan.version + 1)
        revised = retain_completed_steps(state.plan, proposed)
        report = self.plan_validator.validate(
            revised,
            available_tools={spec.name for spec in self.tools.specs()},
        )
        if not report.valid:
            state.trace.emit("replan.rejected", {"errors": list(report.errors)})
            self._checkpoint(state)
            return False
        state.plan = self.scheduler.normalize(revised)
        state.trace.emit(
            "replan.accepted",
            {"plan_id": revised.plan_id, "version": revised.version, "replan_count": state.replan_count},
        )
        self.metrics.increment("agent.replans.accepted")
        self._checkpoint(state)
        return True

    def _finalize(self, state: _RunState) -> AgentResult:
        draft: FinalDraft | None = None
        grounding: GroundingReport | None = None
        attempts = self.config.grounding_repairs + 1
        repair_section: ContextSection | None = None
        for attempt in range(attempts):
            extras = (repair_section,) if repair_section is not None else ()
            packet = self.context.compile(
                system_instruction=self.prompts.system(mode="finalizer"),
                task_instruction=self.prompts.finalization_task(),
                goal=state.inputs.goal,
                namespace=state.inputs.namespace,
                memory=self.memory,
                evidence=state.ledger,
                plan=state.plan,
                observations=state.observations,
                scratchpad=state.scratch,
                extra_sections=extras,
            )
            response = self._model_call(
                state,
                messages=packet.messages(),
                requested_max_tokens=self.config.final_max_tokens,
                response_schema=FINAL_RESPONSE_SCHEMA,
                metadata={"purpose": "finalization", "attempt": attempt + 1, "context": packet.fingerprint},
            )
            draft = FinalDraftDecoder(state.ledger).decode(response.content)
            grounding = GroundingGate(
                state.ledger,
                policy=self.grounding_policy,
                clock=self._wall_clock,
            ).check(draft.claims)
            confidence_ok = draft.confidence >= self.config.minimum_final_confidence
            unresolved_ok = not self.config.fail_on_unresolved or not draft.unresolved
            if grounding.ok and confidence_ok and unresolved_ok:
                break
            repair_section = ContextSection(
                "grounding_repair",
                str(
                    json_safe(
                        {
                            "previous_answer": draft.answer,
                            "rejected_claims": [claim.claim_id for claim in grounding.rejected],
                            "reasons": {key: list(value) for key, value in grounding.reasons.items()},
                            "contradictions": [item.contradiction_id for item in grounding.contradictions],
                            "draft_confidence": draft.confidence,
                            "minimum_confidence": self.config.minimum_final_confidence,
                            "unresolved": list(draft.unresolved),
                            "instruction": "Remove, qualify, or correctly ground unsupported claims. Do not invent evidence IDs.",
                        }
                    )
                ),
                priority=100,
                required=True,
            )
            state.trace.emit(
                "final.grounding_repair",
                {
                    "attempt": attempt + 1,
                    "rejected": len(grounding.rejected),
                    "contradictions": len(grounding.contradictions),
                    "confidence": draft.confidence,
                },
            )
        assert draft is not None and grounding is not None
        if not grounding.ok:
            return self._finish_failure(
                state,
                TerminationReason.GROUNDING_FAILED,
                self._grounding_failure_answer(draft, grounding),
                claims=grounding.accepted,
                metadata={"grounded_fraction": grounding.grounded_fraction},
            )
        if draft.confidence < self.config.minimum_final_confidence:
            return self._finish_failure(
                state,
                TerminationReason.GROUNDING_FAILED,
                draft.answer,
                claims=grounding.accepted,
                metadata={"reason": "final confidence below threshold", "confidence": draft.confidence},
            )
        if self.config.fail_on_unresolved and draft.unresolved:
            return self._finish_failure(
                state,
                TerminationReason.VERIFICATION_FAILED,
                draft.answer,
                claims=grounding.accepted,
                metadata={"unresolved": list(draft.unresolved)},
            )

        if self.config.stage_memory_candidates:
            self._stage_memory_candidates(state, draft)
        if self.config.stage_success_episode:
            evidence_refs = tuple(
                ref
                for claim in grounding.accepted
                for ref in claim.evidence
            )
            self._remember_working(
                state.inputs.namespace,
                f"Completed goal {state.inputs.goal.goal_id}: {draft.answer}",
                kind=MemoryKind.EPISODIC,
                source="verified-run",
                evidence=self._dedupe_refs(evidence_refs),
                tags=("run-result", state.run_id, state.inputs.goal.goal_id),
                trust=min(1.0, max(0.5, draft.confidence)),
                salience=0.7,
            )
        self._transition(state, AgentPhase.COMPLETED)
        state.trace.emit(
            "run.completed",
            {
                "claims": len(grounding.accepted),
                "observations": len(state.observations),
                "usage": self._usage_dict(state.usage),
            },
        )
        self._checkpoint(state)
        self.metrics.increment("agent.runs.succeeded")
        return AgentResult(
            run_id=state.run_id,
            goal_id=state.inputs.goal.goal_id,
            success=True,
            reason=TerminationReason.GOAL_REACHED,
            answer=draft.answer,
            usage=state.usage,
            claims=grounding.accepted,
            observations=tuple(state.observations),
            plan=state.plan,
            trace_fingerprint=self._cumulative_trace_fingerprint(state),
            metadata={
                "confidence": draft.confidence,
                "unresolved": list(draft.unresolved),
                "replans": state.replan_count,
                "evidence_fingerprint": state.ledger.fingerprint,
            },
        )

    def _stage_memory_candidates(self, state: _RunState, draft: FinalDraft) -> None:
        for index, candidate in enumerate(draft.memory_candidates[:32], start=1):
            try:
                content = candidate.get("content")
                if not isinstance(content, str) or not content.strip():
                    continue
                raw_kind = str(candidate.get("kind", MemoryKind.EPISODIC.value))
                kind = MemoryKind(raw_kind)
                if kind is MemoryKind.WORKING:
                    kind = MemoryKind.EPISODIC
                evidence_ids = candidate.get("evidence_ids", [])
                if not isinstance(evidence_ids, list) or any(not isinstance(item, str) for item in evidence_ids):
                    continue
                refs = state.ledger.refs(evidence_ids)
                if kind is MemoryKind.SEMANTIC and not refs:
                    continue
                requested_trust = float(candidate.get("trust", 0.4))
                requested_salience = float(candidate.get("salience", 0.5))
                trust_cap = min((ref.confidence for ref in refs), default=0.45)
                trust = max(0.0, min(1.0, requested_trust, trust_cap, draft.confidence))
                salience = max(0.0, min(1.0, requested_salience))
                record = self.memory.remember(
                    state.inputs.namespace,
                    content,
                    kind=kind,
                    salience=salience,
                    trust=trust,
                    source="model-candidate",
                    evidence=refs,
                    tags=("candidate", state.run_id, f"candidate-{index}"),
                    ttl_seconds=self.config.working_memory_ttl_seconds * 7,
                    metadata={"candidate": True, "final_confidence": draft.confidence},
                )
                state.trace.emit(
                    "memory.candidate_staged",
                    {"memory_id": record.memory_id, "kind": record.kind.value, "trust": record.trust},
                )
            except Exception as exc:
                state.trace.emit(
                    "memory.candidate_rejected",
                    {"index": index, "error": f"{type(exc).__name__}: {str(exc)[:512]}"},
                )

    def _bridge_artifacts(self, state: _RunState, artifacts: Sequence[EvidenceArtifact]) -> None:
        if not self.config.bridge_verified_evidence or self.learning_bridge is None:
            return
        for artifact in artifacts:
            try:
                update = self.learning_bridge.record_artifact(
                    artifact,
                    subject_id=state.inputs.goal.goal_id,
                )
                state.trace.emit(
                    "learning.evidence_bridged",
                    {"evidence_id": artifact.evidence_id, "version": getattr(update, "version", None)},
                )
            except Exception as exc:
                # The learning store is fail-closed (staleness, epoch, payload
                # restrictions).  A rejected bridge must never invalidate the
                # source evidence or silently mutate it.
                state.trace.emit(
                    "learning.evidence_bridge_rejected",
                    {"evidence_id": artifact.evidence_id, "error": f"{type(exc).__name__}: {str(exc)[:512]}"},
                )

    def _model_call(
        self,
        state: _RunState,
        *,
        messages: Sequence[Any],
        requested_max_tokens: int,
        tools: Sequence[Mapping[str, Any]] = (),
        response_schema: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> ModelResponse:
        self._raise_if_cancelled(state)
        if state.usage.model_calls >= state.inputs.budget.max_model_calls:
            raise BudgetExhausted(TerminationReason.MAX_MODEL_CALLS, "model-call budget exhausted")
        remaining_tokens = state.inputs.budget.max_tokens - state.usage.total_tokens
        if remaining_tokens <= 0:
            raise BudgetExhausted(TerminationReason.MAX_TOKENS, "token budget exhausted")
        max_tokens = min(requested_max_tokens, remaining_tokens)
        request = ModelRequest(
            request_id=stable_id(
                "request",
                {
                    "run": state.run_id,
                    "model_call": state.usage.model_calls + 1,
                    "purpose": dict(metadata or {}).get("purpose"),
                    "messages": [(message.role.value, message.content) for message in messages],
                },
            ),
            messages=tuple(messages),
            max_tokens=max_tokens,
            temperature=self.config.model_temperature,
            tools=tuple(tools),
            response_schema=response_schema,
            metadata=dict(metadata or {}),
        )
        state.trace.emit(
            "model.requested",
            {
                "request_id": request.request_id,
                "purpose": request.metadata.get("purpose"),
                "max_tokens": request.max_tokens,
                "tool_schemas": len(request.tools),
            },
        )
        with state.tracer.span("agent.model", purpose=request.metadata.get("purpose", "unknown")):
            response = self.providers.complete(
                request,
                preferred=state.inputs.preferred_provider,
                require_tools=False,
                require_structured_output=False,
            )
        delta = usage_from_response(response)
        state.usage = state.usage.add(
            model_calls=delta.model_calls,
            prompt_tokens=delta.prompt_tokens,
            completion_tokens=delta.completion_tokens,
            cached_model_calls=delta.cached_model_calls,
        )
        self.metrics.increment("agent.model.calls")
        self.metrics.observe("agent.model.latency_ms", response.latency_ms)
        state.trace.emit(
            "model.completed",
            {
                "request_id": request.request_id,
                "provider": response.provider,
                "model": response.model,
                "prompt_tokens": response.prompt_tokens,
                "completion_tokens": response.completion_tokens,
                "cached": response.cached,
                "finish_reason": response.finish_reason,
            },
        )
        if state.usage.total_tokens > state.inputs.budget.max_tokens:
            raise BudgetExhausted(TerminationReason.MAX_TOKENS, "provider response exceeded token budget")
        self._checkpoint(state)
        return response

    def _raise_if_budget_exhausted(self, state: _RunState) -> None:
        budget = state.inputs.budget
        elapsed = max(0.0, self._monotonic() - state.started_monotonic)
        if state.usage.steps >= budget.max_steps:
            raise BudgetExhausted(TerminationReason.MAX_STEPS, "step budget exhausted")
        if state.usage.model_calls >= budget.max_model_calls:
            raise BudgetExhausted(TerminationReason.MAX_MODEL_CALLS, "model-call budget exhausted")
        if state.usage.tool_calls >= budget.max_tool_calls:
            raise BudgetExhausted(TerminationReason.MAX_TOOL_CALLS, "tool-call budget exhausted")
        if state.usage.total_tokens >= budget.max_tokens:
            raise BudgetExhausted(TerminationReason.MAX_TOKENS, "token budget exhausted")
        if elapsed >= budget.max_wall_seconds:
            raise BudgetExhausted(TerminationReason.WALL_CLOCK, "wall-clock budget exhausted")

    def _raise_if_tool_budget_exhausted(self, state: _RunState) -> None:
        if state.usage.tool_calls >= state.inputs.budget.max_tool_calls:
            raise BudgetExhausted(TerminationReason.MAX_TOOL_CALLS, "tool-call budget exhausted")

    def _raise_if_cancelled(self, state: _RunState) -> None:
        if self._cancel_requested(state.run_id):
            raise RunCancelled(state.run_id)

    def _transition(self, state: _RunState, phase: AgentPhase) -> None:
        if state.phase is phase:
            return
        state.trace.emit("run.phase", {"from": state.phase.value, "to": phase.value})
        state.phase = phase
        self._checkpoint(state)

    def _checkpoint(self, state: _RunState) -> RunCheckpoint:
        state.checkpoint_sequence += 1
        scratch = {
            entry.key: {"value": entry.value, "importance": entry.importance}
            for entry in state.scratch.entries()
        }
        checkpoint = RunCheckpoint(
            run_id=state.run_id,
            goal_id=state.inputs.goal.goal_id,
            phase=state.phase,
            sequence=state.checkpoint_sequence,
            usage=state.usage,
            plan=state.plan,
            observations=tuple(state.observations),
            evidence=state.ledger.artifacts(),
            scratch=scratch,
            replan_count=state.replan_count,
            previous_trace_fingerprint=state.previous_trace_fingerprint,
            current_trace_fingerprint=state.trace.fingerprint,
            last_error=state.last_error,
            created_at=state.created_wall,
            updated_at=self._wall_clock(),
            metadata={
                "tenant_id": state.inputs.tenant_id,
                "user_id": state.inputs.user_id,
                "workspace_id": state.inputs.workspace_id,
                "session_id": state.inputs.session_id,
                "evidence_fingerprint": state.ledger.fingerprint,
            },
        )
        self.checkpointer.save(checkpoint)
        self.metrics.increment("agent.checkpoints.saved")
        return checkpoint

    def _finish_failure(
        self,
        state: _RunState,
        reason: TerminationReason,
        answer: str,
        *,
        claims: Sequence[Claim] = (),
        metadata: Mapping[str, Any] | None = None,
        cancelled: bool = False,
        terminal_phase: AgentPhase | None = None,
    ) -> AgentResult:
        phase = terminal_phase or (AgentPhase.CANCELLED if cancelled else AgentPhase.FAILED)
        if state.phase not in {AgentPhase.COMPLETED, AgentPhase.CANCELLED, AgentPhase.FAILED}:
            self._transition(state, phase)
        state.trace.emit(
            "run.terminated",
            {
                "reason": reason.value,
                "phase": state.phase.value,
                "usage": self._usage_dict(state.usage),
                "error": state.last_error,
            },
        )
        self._checkpoint(state)
        self.metrics.increment("agent.runs.failed")
        return AgentResult(
            run_id=state.run_id,
            goal_id=state.inputs.goal.goal_id,
            success=False,
            reason=reason,
            answer=answer,
            usage=state.usage,
            claims=tuple(claims),
            observations=tuple(state.observations),
            plan=state.plan,
            trace_fingerprint=self._cumulative_trace_fingerprint(state),
            metadata={
                **dict(metadata or {}),
                "replans": state.replan_count,
                "evidence_fingerprint": state.ledger.fingerprint,
                "last_error": state.last_error,
            },
        )

    def _remember_working(
        self,
        namespace: MemoryNamespace,
        content: str,
        *,
        kind: MemoryKind = MemoryKind.WORKING,
        source: str,
        tags: Sequence[str],
        trust: float,
        salience: float,
        evidence: Sequence[EvidenceRef] = (),
    ) -> None:
        try:
            self.memory.remember(
                namespace,
                content,
                kind=kind,
                salience=salience,
                trust=trust,
                source=source,
                evidence=evidence,
                tags=tags,
                ttl_seconds=self.config.working_memory_ttl_seconds,
                metadata={"automatic": True, "promoted": False},
            )
        except Exception:
            # Runtime completion must not depend on optional memory persistence.
            self.metrics.increment("agent.memory.write_failures")

    @staticmethod
    def _dedupe_refs(refs: Sequence[EvidenceRef]) -> tuple[EvidenceRef, ...]:
        by_id: dict[str, EvidenceRef] = {}
        for ref in refs:
            prior = by_id.get(ref.evidence_id)
            if prior is not None and prior.fingerprint != ref.fingerprint:
                raise RuntimeErrorBase("conflicting evidence fingerprints in final claims")
            by_id[ref.evidence_id] = ref
        return tuple(by_id[key] for key in sorted(by_id))

    @staticmethod
    def _verification_event(report: VerificationReport | None) -> dict[str, Any]:
        if report is None:
            return {}
        return {
            "step_id": report.step_id,
            "passed": report.passed,
            "score": report.score,
            "failures": [
                {"name": check.name, "severity": check.severity.value, "message": check.message}
                for check in report.failures
            ],
            "evidence_ids": list(report.evidence_ids),
            "contradictions": [item.contradiction_id for item in report.contradictions],
            "fingerprint": report.fingerprint,
        }

    @staticmethod
    def _grounding_failure_answer(draft: FinalDraft, report: GroundingReport) -> str:
        if draft.answer.strip():
            return draft.answer
        if report.accepted:
            return "Some claims were grounded, but the final response failed the grounding gate."
        return "Jeeves could not produce a sufficiently grounded final answer from the available evidence."

    def _cumulative_trace_fingerprint(self, state: _RunState) -> str:
        if state.previous_trace_fingerprint:
            return stable_fingerprint(
                {
                    "previous": state.previous_trace_fingerprint,
                    "current": state.trace.fingerprint,
                }
            )
        return state.trace.fingerprint

    @staticmethod
    def _usage_dict(usage: Usage) -> dict[str, int]:
        return {
            "steps": usage.steps,
            "model_calls": usage.model_calls,
            "tool_calls": usage.tool_calls,
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "cached_model_calls": usage.cached_model_calls,
            "total_tokens": usage.total_tokens,
        }

    @staticmethod
    def _budget_dict(budget: Budget) -> dict[str, Any]:
        return {
            "max_steps": budget.max_steps,
            "max_model_calls": budget.max_model_calls,
            "max_tool_calls": budget.max_tool_calls,
            "max_tokens": budget.max_tokens,
            "max_wall_seconds": budget.max_wall_seconds,
        }
