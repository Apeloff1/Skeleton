from __future__ import annotations

from skeleton.jeeves.agent.epistemic_tool_gate import ToolExecutionIntent
from skeleton.jeeves.agent.model_based_control import TransitionOutcome
from skeleton.jeeves.agent.policy import PolicyDecision
from skeleton.jeeves.agent.runtime_abstraction import (
    ArgumentAbstractor,
    GeneralizingRuntimeEpistemicGuard,
)
from skeleton.jeeves.agent.runtime_guard import (
    GuardAdmissionMode,
    RuntimeGuardRequest,
    RuntimeGuardSignals,
)
from skeleton.jeeves.agent.tools import (
    ArgumentRule,
    ToolExecutionContext,
    ToolExecutor,
    ToolGrant,
    ToolRegistry,
    ToolSpec,
)
from skeleton.jeeves.agent.types import (
    Budget,
    Decision,
    RiskTier,
    ToolCall,
    Usage,
    stable_fingerprint,
)


class Clock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        self.value += 0.01
        return self.value


def _guard():
    clock = Clock()
    calls = []
    registry = ToolRegistry()
    spec = ToolSpec(
        name="update_record",
        description="Update one test record.",
        risk=RiskTier.REVERSIBLE,
        arguments=(
            ArgumentRule("record_id", "string", max_length=128),
            ArgumentRule("amount", "integer", minimum=0, maximum=1_000_000),
        ),
    )
    registry.register(
        spec,
        lambda arguments, context: calls.append(
            (arguments["record_id"], arguments["amount"], context.run_id)
        )
        or {"ok": True, "record_id": arguments["record_id"]},
    )
    executor = ToolExecutor(registry, clock=clock, monotonic=clock)
    return clock, calls, spec, GeneralizingRuntimeEpistemicGuard(
        executor,
        wall_clock=clock,
    )


def _request(
    spec: ToolSpec,
    *,
    run_id: str,
    step_id: str,
    call_id: str,
    record_id: str,
    amount: int,
) -> RuntimeGuardRequest:
    call = ToolCall(
        call_id=call_id,
        name=spec.name,
        arguments={"record_id": record_id, "amount": amount},
    )
    context = ToolExecutionContext(
        run_id=run_id,
        user_id=f"user-{run_id[-1]}",
        trace_id=f"trace-{run_id[-1]}",
    )
    grant = ToolGrant(
        tool_name=spec.name,
        allowed_risks=(RiskTier.REVERSIBLE,),
        max_calls=10,
        argument_fingerprint=stable_fingerprint(call.arguments),
    )
    return RuntimeGuardRequest(
        run_id=run_id,
        goal_id=f"goal-{run_id[-1]}",
        step_id=step_id,
        attempt=1,
        plan_version=1,
        call=call,
        execution_context=context,
        tool_spec=spec,
        grants=(grant,),
        host_policy_decision=PolicyDecision(
            Decision.ALLOW,
            "host allowed",
            "test-policy",
            risk=RiskTier.REVERSIBLE,
        ),
        confirmed_actions=(),
        usage=Usage(),
        budget=Budget(),
        signals=RuntimeGuardSignals(
            progress=0.2,
            uncertainty=0.5,
            budget_pressure=0.1,
            failure_pressure=0.0,
        ),
    )


def _finalize(guard: GeneralizingRuntimeEpistemicGuard, execution):
    refs = execution.observation.evidence
    return guard.finalize(
        execution,
        verification_score=0.95,
        outcome=TransitionOutcome.SUCCESS,
        evidence_ids=tuple(ref.evidence_id for ref in refs),
        evidence_fingerprint=stable_fingerprint(
            [(ref.evidence_id, ref.fingerprint) for ref in refs]
        ),
        signals=RuntimeGuardSignals(
            progress=0.5,
            uncertainty=0.2,
            budget_pressure=0.2,
            failure_pressure=0.0,
        ),
    )


def test_abstractor_never_emits_raw_identifier_email_url_or_path() -> None:
    abstractor = ArgumentAbstractor()
    raw = {
        "uuid": "550e8400-e29b-41d4-a716-446655440000",
        "email": "secret.person@example.com",
        "url": "https://private.example.com/resource/secret-token",
        "path": "/private/customer/secret.txt",
        # Deliberately low-entropy synthetic hex.  It exercises the structural
        # classifier without resembling a credential to repository secret scans.
        "token": "aaaaaaaaaaaaaaaa",
    }

    abstracted = abstractor.abstract(raw)
    rendered = repr(abstracted)

    for secret in raw.values():
        assert secret not in rendered
    assert abstracted["fields"]["uuid"]["structure"] == "uuid"
    assert abstracted["fields"]["email"]["structure"] == "email"
    assert abstracted["fields"]["url"]["structure"] == "url"
    assert abstracted["fields"]["path"]["structure"] == "path"
    assert abstracted["fields"]["token"]["structure"] == "hex_identifier"


def test_numeric_order_of_magnitude_remains_part_of_learning_identity() -> None:
    abstractor = ArgumentAbstractor()

    small = abstractor.abstract({"amount": 7})
    medium = abstractor.abstract({"amount": 70})
    large = abstractor.abstract({"amount": 7000})

    assert small != medium != large
    assert small["fields"]["amount"]["magnitude"] == "1-9"
    assert medium["fields"]["amount"]["magnitude"] == "10-99"
    assert large["fields"]["amount"]["magnitude"] == "1k-9k"


def test_equivalent_resource_ids_share_learning_identity_but_not_exact_intent() -> None:
    _, _, spec, guard = _guard()
    first = _request(
        spec,
        run_id="run-a",
        step_id="step-a",
        call_id="call-a",
        record_id="customer_alpha",
        amount=7,
    )
    second = _request(
        spec,
        run_id="run-b",
        step_id="step-b",
        call_id="call-b",
        record_id="customer_bravo",
        amount=8,
    )

    first_learning = guard.learning_identity(first)
    second_learning = guard.learning_identity(second)

    assert first_learning["state_id"] == second_learning["state_id"]
    assert first_learning["action_id"] == second_learning["action_id"]

    first_intent = ToolExecutionIntent.bind(
        action_id=first_learning["action_id"],
        call=first.call,
        context=first.execution_context,
    )
    second_intent = ToolExecutionIntent.bind(
        action_id=second_learning["action_id"],
        call=second.call,
        context=second.execution_context,
    )
    assert first_intent.fingerprint != second_intent.fingerprint
    assert first_intent.argument_fingerprint != second_intent.argument_fingerprint


def test_different_numeric_scale_does_not_share_action_identity() -> None:
    _, _, spec, guard = _guard()
    small = _request(
        spec,
        run_id="run-a",
        step_id="step-a",
        call_id="call-a",
        record_id="customer_alpha",
        amount=7,
    )
    large = _request(
        spec,
        run_id="run-b",
        step_id="step-b",
        call_id="call-b",
        record_id="customer_bravo",
        amount=7000,
    )

    small_identity = guard.learning_identity(small)
    large_identity = guard.learning_identity(large)

    assert small_identity["action_id"] != large_identity["action_id"]
    assert small_identity["state_id"] != large_identity["state_id"]


def test_learning_generalizes_across_runs_without_reusing_authorization() -> None:
    _, calls, spec, guard = _guard()
    first_request = _request(
        spec,
        run_id="run-a",
        step_id="step-a",
        call_id="call-a",
        record_id="customer_alpha",
        amount=7,
    )
    first = guard.execute(first_request)
    assert first.admission_mode is GuardAdmissionMode.COLD_START_HOST_TRUST
    _finalize(guard, first)

    second_request = _request(
        spec,
        run_id="run-b",
        step_id="step-b",
        call_id="call-b",
        record_id="customer_bravo",
        amount=8,
    )
    second = guard.execute(second_request)

    assert second.admission_mode is GuardAdmissionMode.MODEL_GATED
    assert second.prediction.observations == 1
    assert first.action.action_id == second.action.action_id
    assert first.pre_state.state_id == second.pre_state.state_id
    assert first.intent.fingerprint != second.intent.fingerprint
    assert first.bound_execution.permit.token_id != second.bound_execution.permit.token_id
    assert calls == [
        ("customer_alpha", 7, "run-a"),
        ("customer_bravo", 8, "run-b"),
    ]
    _finalize(guard, second)


def test_argument_shape_change_creates_new_learning_cell() -> None:
    abstractor = ArgumentAbstractor()
    one_field = abstractor.fingerprint({"value": 7})
    two_fields = abstractor.fingerprint({"value": 7, "mode": "fast"})

    assert one_field != two_fields