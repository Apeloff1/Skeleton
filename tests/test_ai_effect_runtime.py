from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import timedelta
import json

import pytest

from skeleton.ai.runtime.effects import (
    ApplyResult,
    BatchState,
    CallbackEffectHandler,
    CallbackEffectVerifier,
    CapabilityAuthorizer,
    CompensationResult,
    CoreExecution,
    DenyAllAuthorizer,
    EffectContractError,
    EffectHandlerRegistry,
    EffectPolicy,
    EffectPolicyError,
    EffectRegistryError,
    GovernedEffectRuntime,
    JsonEffectProposalSource,
    SQLiteEffectLedger,
    VerificationResult,
    digest_json,
)
from skeleton.ai.runtime.effects.contracts import utc_now


@dataclass(slots=True)
class Core:
    document: dict
    execution_id: str = "exec-001"

    async def run(self, request):
        return CoreExecution(
            execution_id=self.execution_id,
            operation_id="op-001",
            tenant_id="tenant-a",
            output_text=json.dumps(self.document, sort_keys=True),
            evidence_digest=digest_json(
                {"request": request, "execution": self.execution_id}
            ),
        )


@dataclass(slots=True)
class Sink:
    calls: list = field(default_factory=list)

    async def commit(self, result):
        self.calls.append(result)


def effect(pid="e1", key="k1", target="x", value=1, **overrides):
    item = {
        "proposal_id": pid,
        "kind": "kv.set",
        "target": target,
        "payload": {"value": value},
        "required_capability": "state.write",
        "idempotency_key": key,
        "postconditions": [
            {"name": "matches", "description": "value matches"}
        ],
        "reversible": True,
        "risk_class": "low",
        "timeout_ms": 5000,
    }
    item.update(overrides)
    return item


def build_runtime(
    tmp_path,
    document,
    *,
    authorizer=None,
    policy=None,
    verifier_pass=True,
):
    state = {}
    history = []

    async def apply(proposal, context):
        old = state.get(proposal.target, {"missing": True})
        state[proposal.target] = proposal.payload["value"]
        history.append(("apply", proposal.proposal_id))
        return ApplyResult(
            executor_id="executor",
            status="applied",
            output={"value": state[proposal.target]},
            compensation_token={"old": old},
        )

    async def compensate(proposal, receipt, context):
        old = receipt.compensation_token["old"]
        if hasattr(old, "get") and old.get("missing"):
            state.pop(proposal.target, None)
        else:
            state[proposal.target] = old
        history.append(("rollback", proposal.proposal_id))
        return CompensationResult(
            executor_id="executor",
            compensated=True,
            output={},
        )

    async def verify(proposal, receipt, context):
        passed = (
            verifier_pass
            and state.get(proposal.target) == proposal.payload["value"]
        )
        history.append(("verify", proposal.proposal_id))
        return VerificationResult(
            verifier_id="verifier",
            passed=passed,
            postconditions={"matches": passed},
            observed={"value": state.get(proposal.target)},
            reason="ok" if passed else "bad",
        )

    registry = EffectHandlerRegistry()
    registry.register(
        "kv.set",
        handler=CallbackEffectHandler(
            "executor",
            apply,
            compensate,
        ),
        verifier=CallbackEffectVerifier(
            "verifier",
            verify,
        ),
    )
    ledger = SQLiteEffectLedger(str(tmp_path / "effects.db"))
    memory, learning = Sink(), Sink()
    runtime = GovernedEffectRuntime(
        core=Core(document),
        proposal_source=JsonEffectProposalSource(),
        authorizer=authorizer
        or CapabilityAuthorizer(
            {"alice": frozenset({"state.write"})}
        ),
        registry=registry,
        ledger=ledger,
        policy=policy
        or EffectPolicy(
            allowed_risk_classes=frozenset({"low"})
        ),
        memory_sink=memory,
        learning_sink=learning,
    )
    return runtime, ledger, state, history, memory, learning


def run(coro):
    return asyncio.run(coro)


def test_happy_path_commits_verified_effect(tmp_path):
    runtime, ledger, state, history, memory, learning = build_runtime(
        tmp_path,
        {"effects": [effect()]},
    )
    result = run(runtime.execute({"x": 1}, subject_id="alice"))
    assert result.state is BatchState.COMMITTED
    assert state == {"x": 1}
    assert [x[0] for x in history] == ["apply", "verify"]
    assert len(result.effects) == 1
    assert (
        result.effects[0].authorization.proposal_digest
        == result.effects[0].proposal.digest
    )
    assert (
        result.effects[0].execution.executor_id
        != result.effects[0].verification.verifier_id
    )
    assert memory.calls == [result]
    assert learning.calls == [result]
    assert (
        ledger.verify_chain(result.transaction_id)
        == result.event_chain_digest
    )


def test_denied_batch_has_zero_side_effects_and_no_learning(tmp_path):
    runtime, _, state, history, memory, learning = build_runtime(
        tmp_path,
        {"effects": [effect()]},
        authorizer=DenyAllAuthorizer(),
    )
    result = run(runtime.execute({}, subject_id="alice"))
    assert result.state is BatchState.REJECTED
    assert state == {}
    assert history == []
    assert memory.calls == learning.calls == []


def test_verification_failure_rolls_back(tmp_path):
    runtime, _, state, history, memory, learning = build_runtime(
        tmp_path,
        {"effects": [effect()]},
        verifier_pass=False,
    )
    result = run(runtime.execute({}, subject_id="alice"))
    assert result.state is BatchState.ROLLED_BACK
    assert state == {}
    assert history == [
        ("apply", "e1"),
        ("verify", "e1"),
        ("rollback", "e1"),
    ]
    assert memory.calls == learning.calls == []


def test_two_effect_batch_rolls_back_in_reverse_order(tmp_path):
    document = {
        "effects": [
            effect("e1", "k1", "a", 1),
            effect("e2", "k2", "b", 2),
        ]
    }
    state = {}
    history = []
    calls = 0

    async def apply(proposal, context):
        old = state.get(proposal.target, {"missing": True})
        state[proposal.target] = proposal.payload["value"]
        history.append(("apply", proposal.proposal_id))
        return ApplyResult(
            "executor",
            "applied",
            {},
            {"old": old},
        )

    async def compensate(proposal, receipt, context):
        state.pop(proposal.target, None)
        history.append(("rollback", proposal.proposal_id))
        return CompensationResult("executor", True, {})

    async def verify(proposal, receipt, context):
        nonlocal calls
        calls += 1
        passed = calls == 1
        history.append(("verify", proposal.proposal_id))
        return VerificationResult(
            "verifier",
            passed,
            {"matches": passed},
            {},
            "ok" if passed else "bad",
        )

    registry = EffectHandlerRegistry()
    registry.register(
        "kv.set",
        handler=CallbackEffectHandler(
            "executor",
            apply,
            compensate,
        ),
        verifier=CallbackEffectVerifier(
            "verifier",
            verify,
        ),
    )
    ledger = SQLiteEffectLedger(str(tmp_path / "x.db"))
    runtime = GovernedEffectRuntime(
        core=Core(document),
        proposal_source=JsonEffectProposalSource(),
        authorizer=CapabilityAuthorizer(
            {"alice": frozenset({"state.write"})}
        ),
        registry=registry,
        ledger=ledger,
        policy=EffectPolicy(
            allowed_risk_classes=frozenset({"low"})
        ),
    )
    result = run(runtime.execute({}, subject_id="alice"))
    assert result.state is BatchState.ROLLED_BACK
    assert state == {}
    assert history[-2:] == [
        ("rollback", "e2"),
        ("rollback", "e1"),
    ]


def test_model_cannot_embed_authorization(tmp_path):
    doc = {
        "effects": [
            effect(authorization={"decision": "allow"})
        ]
    }
    runtime, *_ = build_runtime(tmp_path, doc)
    with pytest.raises(
        EffectContractError,
        match="authority fields forbidden",
    ):
        run(runtime.execute({}, subject_id="alice"))


def test_unknown_fields_fail_closed(tmp_path):
    doc = {"effects": [effect(surprise=True)]}
    runtime, *_ = build_runtime(tmp_path, doc)
    with pytest.raises(
        EffectContractError,
        match="unknown effect fields",
    ):
        run(runtime.execute({}, subject_id="alice"))


def test_missing_capability_rejects_before_apply(tmp_path):
    runtime, _, state, history, *_ = build_runtime(
        tmp_path,
        {"effects": [effect()]},
        authorizer=CapabilityAuthorizer(
            {"alice": frozenset()}
        ),
    )
    result = run(runtime.execute({}, subject_id="alice"))
    assert result.state is BatchState.REJECTED
    assert state == {}
    assert history == []


def test_policy_rejects_irreversible_effect_by_default(tmp_path):
    runtime, *_ = build_runtime(
        tmp_path,
        {"effects": [effect(reversible=False)]},
    )
    with pytest.raises(
        EffectPolicyError,
        match="irreversible",
    ):
        run(runtime.execute({}, subject_id="alice"))


def test_policy_rejects_effect_budget(tmp_path):
    doc = {
        "effects": [
            effect(f"e{i}", f"k{i}", f"x{i}", i)
            for i in range(3)
        ]
    }
    runtime, *_ = build_runtime(
        tmp_path,
        doc,
        policy=EffectPolicy(
            max_effects=2,
            allowed_risk_classes=frozenset({"low"}),
        ),
    )
    with pytest.raises(
        EffectPolicyError,
        match="budget",
    ):
        run(runtime.execute({}, subject_id="alice"))


def test_dry_run_never_authorizes_or_applies(tmp_path):
    runtime, _, state, history, memory, learning = build_runtime(
        tmp_path,
        {"effects": [effect()]},
    )
    result = run(
        runtime.execute(
            {},
            subject_id="alice",
            dry_run=True,
        )
    )
    assert result.state is BatchState.DRY_RUN
    assert state == {}
    assert history == []
    assert memory.calls == []
    assert learning.calls == []


def test_committed_request_replays_without_reapplying(tmp_path):
    runtime, _, state, history, *_ = build_runtime(
        tmp_path,
        {"effects": [effect()]},
    )
    first = run(runtime.execute({}, subject_id="alice"))
    second = run(runtime.execute({}, subject_id="alice"))
    assert first.state is BatchState.COMMITTED
    assert second.replayed is True
    assert history == [
        ("apply", "e1"),
        ("verify", "e1"),
    ]
    assert state == {"x": 1}


def test_event_chain_detects_tampering(tmp_path):
    runtime, ledger, *_ = build_runtime(
        tmp_path,
        {"effects": [effect()]},
    )
    result = run(runtime.execute({}, subject_id="alice"))
    ledger._conn.execute(
        (
            "UPDATE effect_events SET payload_json='{}' "
            "WHERE transaction_id=? AND sequence=1"
        ),
        (result.transaction_id,),
    )
    with pytest.raises(
        Exception,
        match="digest mismatch",
    ):
        ledger.verify_chain(result.transaction_id)


def test_registry_requires_independent_verifier():
    async def apply(proposal, context):
        return ApplyResult("same", "noop", {})

    async def compensate(proposal, receipt, context):
        return CompensationResult("same", True, {})

    async def verify(proposal, receipt, context):
        return VerificationResult(
            "same",
            True,
            {},
            {},
            "ok",
        )

    registry = EffectHandlerRegistry()
    with pytest.raises(
        EffectRegistryError,
        match="must differ",
    ):
        registry.register(
            "x",
            handler=CallbackEffectHandler(
                "same",
                apply,
                compensate,
            ),
            verifier=CallbackEffectVerifier(
                "same",
                verify,
            ),
        )


def test_expired_deadline_fails_before_core(tmp_path):
    runtime, *_ = build_runtime(
        tmp_path,
        {"effects": [effect()]},
    )
    with pytest.raises(Exception, match="deadline"):
        run(
            runtime.execute(
                {},
                subject_id="alice",
                deadline=utc_now() - timedelta(seconds=1),
            )
        )


def test_qualification_script_contract(tmp_path):
    from skeleton.ai.runtime.effects.qualification import run_qualification

    report = run_qualification(str(tmp_path / "qual.db"))
    assert report["passed"] is True
    assert all(report["proofs"].values())



def test_apply_failure_is_in_doubt_and_partial_failure(tmp_path):
    state = {}

    async def apply(proposal, context):
        state[proposal.target] = proposal.payload["value"]
        raise RuntimeError("lost acknowledgement")

    async def compensate(proposal, receipt, context):
        raise AssertionError(
            "no receipt means compensation must not guess"
        )

    async def verify(proposal, receipt, context):
        raise AssertionError(
            "unreceipted effect must not verify"
        )

    registry = EffectHandlerRegistry()
    registry.register(
        "kv.set",
        handler=CallbackEffectHandler(
            "executor",
            apply,
            compensate,
        ),
        verifier=CallbackEffectVerifier(
            "verifier",
            verify,
        ),
    )
    ledger = SQLiteEffectLedger(
        str(tmp_path / "indoubt.db")
    )
    memory, learning = Sink(), Sink()
    runtime = GovernedEffectRuntime(
        core=Core({"effects": [effect()]}),
        proposal_source=JsonEffectProposalSource(),
        authorizer=CapabilityAuthorizer(
            {"alice": frozenset({"state.write"})}
        ),
        registry=registry,
        ledger=ledger,
        policy=EffectPolicy(
            allowed_risk_classes=frozenset({"low"})
        ),
        memory_sink=memory,
        learning_sink=learning,
    )
    result = run(
        runtime.execute({}, subject_id="alice")
    )
    assert result.state is BatchState.PARTIAL_FAILURE
    assert "e1" in result.reason
    assert state == {"x": 1}
    assert memory.calls == []
    assert learning.calls == []


def test_global_deadline_bounds_verifier_and_rolls_back(
    tmp_path,
    monkeypatch,
):
    state = {}
    fixed_now = utc_now()
    monkeypatch.setattr(
        "skeleton.ai.runtime.effects.runtime.utc_now",
        lambda: fixed_now,
    )
    monkeypatch.setattr(
        "skeleton.ai.runtime.effects.registry.utc_now",
        lambda: fixed_now,
    )

    async def apply(proposal, context):
        state[proposal.target] = proposal.payload["value"]
        return ApplyResult(
            "executor",
            "applied",
            {},
            {"old": {"missing": True}},
        )

    async def compensate(proposal, receipt, context):
        state.pop(proposal.target, None)
        return CompensationResult(
            "executor",
            True,
            {},
        )

    async def verify(proposal, receipt, context):
        await asyncio.sleep(0.05)
        return VerificationResult(
            "verifier",
            True,
            {"matches": True},
            {},
            "late",
        )

    registry = EffectHandlerRegistry()
    registry.register(
        "kv.set",
        handler=CallbackEffectHandler(
            "executor",
            apply,
            compensate,
        ),
        verifier=CallbackEffectVerifier(
            "verifier",
            verify,
        ),
    )
    ledger = SQLiteEffectLedger(
        str(tmp_path / "deadline.db")
    )
    runtime = GovernedEffectRuntime(
        core=Core({"effects": [effect()]}),
        proposal_source=JsonEffectProposalSource(),
        authorizer=CapabilityAuthorizer(
            {"alice": frozenset({"state.write"})}
        ),
        registry=registry,
        ledger=ledger,
        policy=EffectPolicy(
            allowed_risk_classes=frozenset({"low"})
        ),
    )
    result = run(
        runtime.execute(
            {},
            subject_id="alice",
            deadline=(
                fixed_now
                + timedelta(milliseconds=15)
            ),
        )
    )
    assert result.state is BatchState.ROLLED_BACK
    assert state == {}
    assert "verification failed" in result.reason


def test_authorizer_failure_records_terminal_failure_without_effect(
    tmp_path,
):
    class BrokenAuthorizer:
        async def authorize(
            self,
            proposal,
            *,
            subject_id,
            now,
        ):
            raise RuntimeError(
                "policy backend unavailable"
            )

    runtime, ledger, state, history, memory, learning = (
        build_runtime(
            tmp_path,
            {"effects": [effect()]},
            authorizer=BrokenAuthorizer(),
        )
    )
    result = run(
        runtime.execute({}, subject_id="alice")
    )
    assert result.state is BatchState.FAILED
    assert "policy backend unavailable" in result.reason
    assert state == {}
    assert history == []
    assert memory.calls == []
    assert learning.calls == []
    assert (
        ledger.verify_chain(result.transaction_id)
        == result.event_chain_digest
    )
