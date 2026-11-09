from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from pathlib import Path

import pytest

from skeleton.ai.runtime.deferred import (
    DeferredExecutionError,
    DeferredExecutionPendingError,
    DeferredExecutor,
    DeferredJournalConflict,
    SqliteDeferredExecutionJournal,
    DeferredInvocation,
    build_registry,
    volume_ids,
)
from skeleton.ai.runtime.deferred.compute import (
    EthicsReview,
    FarmTask,
    GPUMemoryManager,
    GPUReservation,
    KVCacheKey,
    ResearchProposal,
    SandboxManifest,
    WorkFarm,
    WorkerAttestation,
)
from skeleton.ai.runtime.deferred.contracts import (
    Budget,
    BudgetLedger,
    EvidenceReceipt,
    canonical_json,
    sha256_json,
)
from skeleton.ai.runtime.deferred.knowledge import (
    Claim,
    ClaimReconciler,
    ClaimScope,
    EmbeddingIdentity,
    MemoryRevision,
    SourceEvidence,
    VersionedMemory,
)
from skeleton.ai.runtime.deferred.operations_experience import (
    AuditEvent,
    AuditLog,
    FuzzReproducer,
    TrustSignal,
)
from skeleton.ai.runtime.deferred.platform_control import (
    ApprovalFatigueGuard,
    Constraint,
    DecisionCandidate,
    DecisionEngine,
    DeploymentPlanner,
    DeploymentTarget,
    FederatedIdentity,
    Objective,
    StableIdentifier,
)
from skeleton.ai.runtime.deferred.reliability_release import (
    CircuitBreaker,
    CircuitState,
    CongestionController,
    ErrorBudget,
    LogicalClock,
    OperationReplayLedger,
    ReleaseQualification,
    ReleaseRequirement,
    RetryBudget,
    SLOSpec,
)
from skeleton.ai.runtime.deferred.research_evaluation import (
    ContaminationAuditor,
    EvalCase,
    EvalOutcome,
    EvaluationHarness,
    HumanEvaluation,
    HumanJudgment,
    ProviderFailover,
    ProviderRisk,
)
from skeleton.ai.runtime.deferred.tooling_security import (
    DeletionGraph,
    PluginManifest,
    PluginRegistry,
    PrivacyClass,
    PrivacyLabel,
    ToolContract,
    ToolGrant,
    ToolSDK,
    TrustTier,
)


ROOT = Path(__file__).resolve().parents[2]
HEX_A = "a" * 64
HEX_B = "b" * 64
HEX_C = "c" * 64
HEAD = "d" * 40


def test_deferred_catalog_conserves_exact_canonical_165() -> None:
    frontier = json.loads(
        (ROOT / "machine/ai_masterplan_continuation_frontier.json").read_text(
            encoding="utf-8"
        )
    )
    expected = tuple(frontier["next_tranche"]["queued_volume_refs"])
    assert len(expected) == 165
    assert len(expected) == len(set(expected))
    assert set(volume_ids()) == set(expected)
    assert len(volume_ids()) == 165


def test_execution_map_has_no_completion_or_promotion_authority() -> None:
    payload = json.loads(
        (ROOT / "machine/ai_deferred_165_execution_map.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["expected_volume_count"] == 165
    assert payload["completion_authority"] is False
    assert payload["implementation_status"] == "branch_candidate"
    assert len(payload["volumes"]) == 165
    assert all(row["completion_claim"] is False for row in payload["volumes"])
    assert all(row["promotion_authority"] is False for row in payload["volumes"])


def test_registry_requires_candidate_then_verified_evidence_before_enable() -> None:
    registry = build_registry()
    record = registry.get("VOL-160")

    candidate = EvidenceReceipt(
        volume_id="VOL-160",
        head_sha=HEAD,
        artifact_digests=(HEX_A,),
        tests=("pytest:test_tool_sdk",),
        status="implementation_candidate",
    )
    record.candidate(candidate)
    assert record.state == "implementation_candidate"

    with pytest.raises(ValueError, match="verified receipt"):
        record.verify(candidate)

    verified = EvidenceReceipt(
        volume_id="VOL-160",
        head_sha=HEAD,
        artifact_digests=(HEX_A, HEX_B),
        tests=("pytest:test_tool_sdk", "ci:exact-head"),
        status="verified",
    )
    record.verify(verified)
    assert record.state == "verified"
    registry.enable("VOL-160")
    assert record.state == "enabled"


def test_budget_ledger_fails_closed_before_overspend() -> None:
    ledger = BudgetLedger(Budget(max_attempts=2, max_cost_units=4, max_latency_ms=20))
    ledger.admit(cost_units=2, latency_ms=8)
    ledger.admit(cost_units=2, latency_ms=8)
    assert ledger.cost_units == 4
    assert ledger.attempts == 2
    with pytest.raises(RuntimeError, match="attempt budget exhausted"):
        ledger.admit()


def test_tool_sdk_never_self_authorizes_effect_or_capability() -> None:
    sdk = ToolSDK()
    contract = ToolContract(
        tool_id="repo.write",
        version="1",
        effect="write",
        input_schema_digest=HEX_A,
        required_capabilities=("repo:write",),
    )
    sdk.register(contract, lambda args: args["value"])

    read_only = ToolGrant(
        principal_id="worker",
        tool_id="repo.write",
        allowed_effects=("read",),
        capabilities=("repo:write",),
    )
    with pytest.raises(PermissionError, match="effect"):
        sdk.invoke(contract.identity, read_only, {"value": 1})

    missing_capability = ToolGrant(
        principal_id="worker",
        tool_id="repo.write",
        allowed_effects=("write",),
        capabilities=(),
    )
    with pytest.raises(PermissionError, match="missing tool capabilities"):
        sdk.invoke(contract.identity, missing_capability, {"value": 1})

    granted = ToolGrant(
        principal_id="worker",
        tool_id="repo.write",
        allowed_effects=("write",),
        capabilities=("repo:write",),
    )
    assert sdk.invoke(contract.identity, granted, {"value": 7}) == 7


def test_plugin_registry_rejects_low_trust_and_revoked_identity() -> None:
    registry = PluginRegistry(minimum_trust=TrustTier.VERIFIED)
    weak = PluginManifest(
        plugin_id="weak",
        version="1",
        trust_tier=TrustTier.UNVERIFIED,
        tool_identities=(),
        requested_capabilities=(),
    )
    with pytest.raises(PermissionError, match="trust tier"):
        registry.install(weak)

    trusted = PluginManifest(
        plugin_id="safe",
        version="1",
        trust_tier=TrustTier.VERIFIED,
        tool_identities=("repo.read@1",),
        requested_capabilities=("repo:read",),
    )
    registry.install(trusted)
    registry.revoke("safe")
    with pytest.raises(PermissionError, match="revoked"):
        registry.install(trusted)


def test_privacy_labels_prevent_downgrade_and_cross_tenant_flow() -> None:
    source = PrivacyLabel(
        PrivacyClass.CONFIDENTIAL,
        purposes=("support", "quality"),
        tenant_id="tenant-a",
    )
    assert not source.can_flow_to(
        PrivacyLabel(PrivacyClass.INTERNAL, purposes=("support",))
    )
    assert not source.can_flow_to(
        PrivacyLabel(
            PrivacyClass.RESTRICTED,
            purposes=("support",),
            tenant_id="tenant-b",
        )
    )
    assert source.can_flow_to(
        PrivacyLabel(
            PrivacyClass.RESTRICTED,
            purposes=("support",),
            tenant_id="tenant-a",
        )
    )


def test_deletion_graph_deletes_derivatives_before_source() -> None:
    graph = DeletionGraph()
    graph.add("source")
    graph.add("embedding", derived_from=("source",))
    graph.add("index", derived_from=("embedding",))
    graph.add("summary", derived_from=("source",))
    order = graph.cascade("source")
    assert order[-1] == "source"
    assert order.index("index") < order.index("embedding") < order.index("source")
    assert order.index("summary") < order.index("source")


def test_error_budget_release_gate_and_reliability_controls() -> None:
    budget = ErrorBudget(SLOSpec("api", target=0.99, window_seconds=60, indicator="success"))
    for _ in range(99):
        budget.observe(True)
    budget.observe(False)
    assert budget.success_ratio == 0.99
    assert budget.remaining == pytest.approx(0.0)

    gates = ReleaseQualification(
        (ReleaseRequirement("tests"), ReleaseRequirement("security"))
    )
    assert gates.qualify({"tests": "success", "security": "success"}) == (True, ())
    ok, blockers = gates.qualify({"tests": "success", "security": "cancelled"})
    assert not ok
    assert blockers == ("security:cancelled",)

    retries = RetryBudget(2)
    assert retries.consume() == 1
    assert retries.consume() == 2
    with pytest.raises(RuntimeError, match="exhausted"):
        retries.consume()

    breaker = CircuitBreaker(failure_threshold=2)
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state is CircuitState.OPEN
    breaker.probe()
    breaker.record_success()
    assert breaker.state is CircuitState.CLOSED

    controller = CongestionController(soft_limit=10, hard_limit=20)
    assert controller.action(5) == "admit"
    assert controller.action(10) == "throttle"
    assert controller.action(20) == "shed"


def test_operation_replay_and_logical_clock_are_deterministic() -> None:
    ledger = OperationReplayLedger()
    digest = ledger.accept("op-1", {"a": 1})
    assert digest == ledger.accept("op-1", {"a": 1})
    with pytest.raises(ValueError, match="collision"):
        ledger.accept("op-1", {"a": 2})

    clock = LogicalClock()
    assert clock.tick() == 1
    assert clock.merge(7) == 8
    assert clock.tick() == 9


def test_evaluation_requires_every_case_and_detects_contamination() -> None:
    cases = (
        EvalCase("a", HEX_A, HEX_B),
        EvalCase("b", HEX_B, HEX_C),
    )
    harness = EvaluationHarness(cases)
    with pytest.raises(ValueError, match="every case"):
        harness.evaluate((EvalOutcome("a", HEX_C, 1.0),))

    result = harness.evaluate(
        (
            EvalOutcome("a", HEX_C, 1.0),
            EvalOutcome("b", HEX_A, 0.5),
        )
    )
    assert result["count"] == 2.0
    assert result["mean_score"] == pytest.approx(0.75)

    assert ContaminationAuditor.overlaps((HEX_A, HEX_B), (HEX_C, HEX_B)) == (HEX_B,)


def test_provider_failover_never_uses_policy_incompatible_fallback() -> None:
    providers = (
        ProviderRisk("cheap", 0.2, ("public",), ("eu",), True),
        ProviderRisk("safe", 0.1, ("confidential",), ("eu",), True),
        ProviderRisk("wrong-region", 0.0, ("confidential",), ("us",), True),
    )
    chosen = ProviderFailover().choose(
        providers,
        required_data_class="confidential",
        allowed_regions=("eu",),
        max_risk=0.2,
    )
    assert chosen.provider_id == "safe"


def test_platform_identity_deployment_and_decision_constraints() -> None:
    identity = StableIdentifier("model", "local", 3)
    assert identity.value == "model:local:v3"
    federation = FederatedIdentity("issuer", "subject", "tenant", 3, HEX_A)
    assert federation.tenant_id == "tenant"

    target = DeploymentPlanner.choose(
        (
            DeploymentTarget("a", "eu", 10, 9, True),
            DeploymentTarget("b", "eu", 10, 2, True),
            DeploymentTarget("c", "us", 100, 0, True),
        ),
        required_units=5,
        allowed_regions=("eu",),
    )
    assert target.target_id == "b"

    decision = DecisionEngine().decide(
        (Objective("quality", 1.0, 2), Objective("cost", -1.0, 1)),
        (Constraint("latency-bound", "latency", "<=", 10),),
        (
            DecisionCandidate(
                "fast",
                objective_scores={"quality": 0.8, "cost": 0.2},
                constraint_values={"latency": 5},
            ),
            DecisionCandidate(
                "slow",
                objective_scores={"quality": 1.0, "cost": 0.1},
                constraint_values={"latency": 20},
            ),
        ),
        decision_id="route-1",
    )
    assert decision.candidate_id == "fast"


def test_memory_versioning_never_resurrects_tombstone() -> None:
    store = VersionedMemory()
    first = MemoryRevision("memory-1", 1, HEX_A, None)
    store.append(first)
    tombstone = MemoryRevision("memory-1", 2, HEX_B, first.digest, tombstone=True)
    store.append(tombstone)
    with pytest.raises(ValueError, match="cannot be resurrected"):
        store.append(
            MemoryRevision(
                "memory-1",
                3,
                HEX_C,
                tombstone.digest,
                tombstone=False,
            )
        )


def test_claim_reconciliation_keeps_scope_and_surfaces_conflict() -> None:
    scope = ClaimScope("adults", "NO", 1, 100)
    claims = (
        Claim("c1", HEX_A, "same", scope, ("s1",), 0.7),
        Claim("c2", HEX_A, "same", scope, ("s1", "s2"), 0.8),
        Claim("c3", HEX_B, "same", scope, ("s3",), 0.9),
    )
    deduped = ClaimReconciler.deduplicate(claims)
    assert len(deduped) == 2
    assert {item.claim_id for item in deduped} == {"c2", "c3"}
    assert ClaimReconciler.conflicts(claims) == (("c1", "c2", "c3"),)

    other_scope = ClaimScope("children", "NO", 1, 100)
    scoped = claims + (
        Claim("c4", HEX_C, "same", other_scope, ("s4",), 0.95),
    )
    assert ClaimReconciler.conflicts(scoped) == (("c1", "c2", "c3"),)


def test_embedding_identity_binds_dimensions_and_source() -> None:
    identity = EmbeddingIdentity(
        "embedder",
        HEX_A,
        768,
        "l2",
        HEX_B,
    )
    assert len(identity.digest) == 64
    with pytest.raises(ValueError, match="dimensions"):
        EmbeddingIdentity("bad", HEX_A, 0, "l2", HEX_B)


def test_gpu_and_cache_governance_prevent_unsafe_reuse() -> None:
    manager = GPUMemoryManager(100)
    manager.reserve(GPUReservation("r1", "model-a", 80))
    with pytest.raises(RuntimeError, match="capacity"):
        manager.reserve(GPUReservation("r2", "model-b", 30))

    key_a = KVCacheKey(HEX_A, HEX_B, HEX_C, "tenant-a")
    key_b = KVCacheKey(HEX_A, HEX_B, HEX_C, "tenant-b")
    assert key_a.digest != key_b.digest

    with pytest.raises(ValueError, match="tenant_id"):
        from skeleton.ai.runtime.deferred.compute import PrefixCacheKey
        PrefixCacheKey(HEX_A, HEX_B, HEX_C, "restricted")


def test_attested_farm_ethics_and_sandbox_authority() -> None:
    farm = WorkFarm(
        (
            WorkerAttestation("w1", HEX_A, HEX_B, True),
            WorkerAttestation("w2", HEX_A, HEX_B, False),
        )
    )
    assigned = farm.assign(FarmTask("task", "eval", HEX_A, 1, "research"))
    assert assigned == "w1"

    proposal = ResearchProposal(
        "proposal",
        "study",
        ("restricted",),
        human_subjects=False,
        autonomous_actions=False,
    )
    assert EthicsReview.required(proposal)

    with pytest.raises(ValueError, match="promotion authority"):
        SandboxManifest(
            "sandbox",
            "feature",
            expires_at=100,
            network_enabled=False,
            write_authority=False,
            promotion_authority=True,
        )


def test_audit_log_is_gapless_and_trust_signal_is_evidence_bounded() -> None:
    log = AuditLog()
    log.append(AuditEvent(1, "e1", "operator", "read", "model", HEX_A))
    with pytest.raises(ValueError, match="sequence gap"):
        log.append(AuditEvent(3, "e3", "operator", "write", "model", HEX_B))

    signal = TrustSignal("confidence", 0.95, 0, warning="no evidence")
    assert signal.display_confidence == 0.0


def test_fuzz_reproducer_identity_is_stable() -> None:
    repro = FuzzReproducer("contract", 42, HEX_A, HEX_B)
    assert repro.digest == FuzzReproducer("contract", 42, HEX_A, HEX_B).digest

def test_human_evaluation_rejects_duplicate_rater_weighting() -> None:
    judgments=(
        HumanJudgment("r1","case","rubric-1",0.9),
        HumanJudgment("r1","case","rubric-1",0.1),
        HumanJudgment("r2","case","rubric-1",0.8),
    )
    with pytest.raises(ValueError,match="duplicate evaluator"):
        HumanEvaluation.aggregate(judgments,min_raters=2)


def test_approval_fatigue_window_recovers_without_suppressing_high_impact() -> None:
    guard=ApprovalFatigueGuard(window=3,max_prompts=2)
    assert guard.request(False)=="prompt"
    assert guard.request(False)=="prompt"
    assert guard.request(False)=="batch_or_defer"
    assert guard.request(False)=="batch_or_defer"
    assert guard.request(False)=="prompt"
    assert guard.request(True)=="prompt"

def _enable_volume(registry, volume_id: str):
    record=registry.get(volume_id)
    candidate=EvidenceReceipt(
        volume_id=volume_id,
        head_sha=HEAD,
        artifact_digests=(HEX_A,),
        tests=("candidate:test",),
        status="implementation_candidate",
    )
    verified=EvidenceReceipt(
        volume_id=volume_id,
        head_sha=HEAD,
        artifact_digests=(HEX_A,HEX_B),
        tests=("candidate:test","verified:test"),
        status="verified",
    )
    record.candidate(candidate)
    record.verify(verified)
    registry.enable(volume_id)
    return record


def _invocation(record, operation_id: str, payload: dict, *, cost: int = 1, latency: int = 1):
    return DeferredInvocation(
        operation_id=operation_id,
        volume_id=record.spec.volume_id,
        spec_digest=record.spec.digest,
        authority_digest=DeferredExecutor.authority_digest(record),
        payload_digest=DeferredExecutor.digest_payload(payload),
        cost_units=cost,
        latency_ms=latency,
    )


def test_deferred_executor_refuses_disabled_capability_before_handler() -> None:
    registry=build_registry()
    record=registry.get("VOL-160")
    calls=[]
    executor=DeferredExecutor(registry)
    executor.register_handler(
        "VOL-160",
        lambda payload: calls.append(payload) or {"ok":True},
        handler_identity=record.spec.handler,
    )
    executor.set_budget(
        "VOL-160",
        Budget(max_attempts=1,max_cost_units=2,max_latency_ms=10),
    )
    payload={"value":1}
    invocation=_invocation(record,"disabled",payload)

    with pytest.raises(PermissionError,match="not enabled"):
        executor.execute(invocation,payload)

    assert calls==[]


def test_deferred_executor_refuses_handler_identity_drift() -> None:
    registry=build_registry()
    record=_enable_volume(registry,"VOL-160")
    executor=DeferredExecutor(registry)

    with pytest.raises(ValueError,match="canonical capability handler"):
        executor.register_handler(
            "VOL-160",
            lambda payload: payload,
            handler_identity="evil.handler",
        )

    assert record.state=="enabled"


def test_deferred_executor_requires_explicit_budget_before_effect() -> None:
    registry=build_registry()
    record=_enable_volume(registry,"VOL-160")
    calls=[]
    executor=DeferredExecutor(registry)
    executor.register_handler(
        "VOL-160",
        lambda payload: calls.append(payload) or {"ok":True},
        handler_identity=record.spec.handler,
    )
    payload={"value":1}

    with pytest.raises(PermissionError,match="execution budget"):
        executor.execute(_invocation(record,"no-budget",payload),payload)

    assert calls==[]


def test_deferred_executor_rejects_payload_or_spec_drift_before_effect() -> None:
    registry=build_registry()
    record=_enable_volume(registry,"VOL-160")
    calls=[]
    executor=DeferredExecutor(registry)
    executor.register_handler(
        "VOL-160",
        lambda payload: calls.append(payload) or {"ok":True},
        handler_identity=record.spec.handler,
    )
    executor.set_budget(
        "VOL-160",
        Budget(max_attempts=1,max_cost_units=2,max_latency_ms=10),
    )
    payload={"value":1}
    invocation=_invocation(record,"digest-drift",payload)

    with pytest.raises(ValueError,match="payload digest mismatch"):
        executor.execute(invocation,{"value":2})

    bad=DeferredInvocation(
        operation_id="spec-drift",
        volume_id=record.spec.volume_id,
        spec_digest=HEX_C,
        authority_digest=DeferredExecutor.authority_digest(record),
        payload_digest=DeferredExecutor.digest_payload(payload),
        cost_units=1,
        latency_ms=1,
    )
    with pytest.raises(PermissionError,match="spec digest drift"):
        executor.execute(bad,payload)

    assert calls==[]


def test_deferred_executor_enforces_budget_before_effect() -> None:
    registry=build_registry()
    record=_enable_volume(registry,"VOL-160")
    calls=[]
    executor=DeferredExecutor(registry)
    executor.register_handler(
        "VOL-160",
        lambda payload: calls.append(payload) or {"ok":True},
        handler_identity=record.spec.handler,
    )
    executor.set_budget(
        "VOL-160",
        Budget(max_attempts=1,max_cost_units=1,max_latency_ms=5),
    )
    payload={"value":1}

    with pytest.raises(RuntimeError,match="cost budget exhausted"):
        executor.execute(
            _invocation(record,"over-budget",payload,cost=2,latency=1),
            payload,
        )

    assert calls==[]


def test_deferred_executor_success_is_idempotent_and_content_bound() -> None:
    registry=build_registry()
    record=_enable_volume(registry,"VOL-160")
    calls=[]
    executor=DeferredExecutor(registry)

    def handler(payload):
        calls.append(payload)
        payload["value"]=999
        return {"answer":42}

    executor.register_handler(
        "VOL-160",
        handler,
        handler_identity=record.spec.handler,
    )
    executor.set_budget(
        "VOL-160",
        Budget(max_attempts=1,max_cost_units=2,max_latency_ms=10),
    )
    payload={"value":1}
    invocation=_invocation(record,"same-op",payload)

    first=executor.execute(invocation,payload)
    first.result["answer"]=0
    second=executor.execute(invocation,payload)

    assert first.receipt==second.receipt
    assert second.receipt.status=="succeeded"
    assert second.receipt.attempt==1
    assert second.receipt.result_digest==DeferredExecutor.digest_payload({"answer":42})
    assert second.result=={"answer":42}
    assert calls==[{"value":999}]
    assert payload=={"value":1}


def test_deferred_executor_rejects_operation_identity_collision() -> None:
    registry=build_registry()
    record=_enable_volume(registry,"VOL-160")
    executor=DeferredExecutor(registry)
    executor.register_handler(
        "VOL-160",
        lambda payload: {"ok":True},
        handler_identity=record.spec.handler,
    )
    executor.set_budget(
        "VOL-160",
        Budget(max_attempts=1,max_cost_units=3,max_latency_ms=10),
    )
    one={"value":1}
    two={"value":2}
    executor.execute(_invocation(record,"collision",one),one)

    with pytest.raises(ValueError,match="operation identity collision"):
        executor.execute(_invocation(record,"collision",two),two)


def test_deferred_executor_failure_is_terminal_and_message_is_not_stored() -> None:
    registry=build_registry()
    record=_enable_volume(registry,"VOL-160")
    calls=[]
    executor=DeferredExecutor(registry)

    def broken(payload):
        calls.append(payload)
        raise RuntimeError("super secret provider detail")

    executor.register_handler(
        "VOL-160",
        broken,
        handler_identity=record.spec.handler,
    )
    executor.set_budget(
        "VOL-160",
        Budget(max_attempts=1,max_cost_units=4,max_latency_ms=20),
    )
    payload={"value":1}
    invocation=_invocation(record,"terminal-failure",payload)

    with pytest.raises(DeferredExecutionError) as first:
        executor.execute(invocation,payload)
    failure=first.value.receipt
    assert failure.status=="failed"
    assert failure.error_type=="RuntimeError"
    assert "super secret" not in json.dumps(failure.as_dict())

    with pytest.raises(DeferredExecutionError,match="previously failed") as second:
        executor.execute(invocation,payload)

    assert second.value.receipt==failure
    assert calls==[{"value":1}]


def test_deferred_executor_rejects_noncanonical_result_as_terminal_failure() -> None:
    registry=build_registry()
    record=_enable_volume(registry,"VOL-160")
    executor=DeferredExecutor(registry)
    executor.register_handler(
        "VOL-160",
        lambda payload: {"bad":float("nan")},
        handler_identity=record.spec.handler,
    )
    executor.set_budget(
        "VOL-160",
        Budget(max_attempts=1,max_cost_units=2,max_latency_ms=10),
    )
    payload={"value":1}
    invocation=_invocation(record,"nan-result",payload)

    with pytest.raises(DeferredExecutionError) as exc:
        executor.execute(invocation,payload)

    assert exc.value.receipt.error_type=="ValueError"
    assert executor.receipt("nan-result")==exc.value.receipt


def test_deferred_executor_snapshot_is_deterministic() -> None:
    registry=build_registry()
    record=_enable_volume(registry,"VOL-160")
    executor=DeferredExecutor(registry)
    executor.register_handler(
        "VOL-160",
        lambda payload: {"echo":payload["value"]},
        handler_identity=record.spec.handler,
    )
    executor.set_budget(
        "VOL-160",
        Budget(max_attempts=1,max_cost_units=5,max_latency_ms=10),
    )
    for operation_id,value in (("b",2),("a",1)):
        payload={"value":value}
        executor.execute(_invocation(record,operation_id,payload),payload)

    first=executor.snapshot()
    second=executor.snapshot()
    assert first==second
    assert [row["receipt"]["operation_id"] for row in first["operations"]]==["a","b"]
    assert len(first["snapshot_digest"])==64

def test_deferred_executor_rejects_multi_attempt_budget_policy() -> None:
    registry=build_registry()
    _enable_volume(registry,"VOL-160")
    executor=DeferredExecutor(registry)

    with pytest.raises(ValueError,match="max_attempts=1"):
        executor.set_budget(
            "VOL-160",
            Budget(max_attempts=2,max_cost_units=4,max_latency_ms=20),
        )


def test_deferred_executor_rejects_stale_authority_evidence_before_effect() -> None:
    registry=build_registry()
    record=_enable_volume(registry,"VOL-160")
    calls=[]
    executor=DeferredExecutor(registry)
    executor.register_handler(
        "VOL-160",
        lambda payload: calls.append(payload) or {"ok":True},
        handler_identity=record.spec.handler,
    )
    executor.set_budget(
        "VOL-160",
        Budget(max_attempts=1,max_cost_units=2,max_latency_ms=10),
    )
    payload={"value":1}
    invocation=_invocation(record,"authority-drift",payload)

    record.attach(
        EvidenceReceipt(
            volume_id="VOL-160",
            head_sha=HEAD,
            artifact_digests=(HEX_C,),
            tests=("late:evidence",),
            status="verified",
        )
    )

    with pytest.raises(PermissionError,match="authority digest drift"):
        executor.execute(invocation,payload)

    assert calls==[]

def test_deferred_executor_rejects_non_string_json_keys() -> None:
    registry=build_registry()
    record=_enable_volume(registry,"VOL-160")
    executor=DeferredExecutor(registry)
    executor.register_handler(
        "VOL-160",
        lambda payload: {"ok":True},
        handler_identity=record.spec.handler,
    )
    executor.set_budget(
        "VOL-160",
        Budget(max_attempts=1,max_cost_units=2,max_latency_ms=10),
    )

    with pytest.raises(TypeError,match="JSON object keys must be strings"):
        DeferredExecutor.digest_payload({1:"value"})


def test_deferred_executor_rejects_oversized_payload_before_effect() -> None:
    registry=build_registry()
    record=_enable_volume(registry,"VOL-160")
    calls=[]
    executor=DeferredExecutor(registry)
    executor.register_handler(
        "VOL-160",
        lambda payload: calls.append(payload) or {"ok":True},
        handler_identity=record.spec.handler,
    )
    executor.set_budget(
        "VOL-160",
        Budget(max_attempts=1,max_cost_units=2,max_latency_ms=10),
        max_payload_bytes=32,
        max_result_bytes=128,
    )
    payload={"value":"x"*64}
    invocation=_invocation(record,"large-payload",payload)

    with pytest.raises(RuntimeError,match="payload byte limit exceeded"):
        executor.execute(invocation,payload)

    assert calls==[]


def test_deferred_executor_records_oversized_result_as_terminal_failure() -> None:
    registry=build_registry()
    record=_enable_volume(registry,"VOL-160")
    calls=[]
    executor=DeferredExecutor(registry)
    executor.register_handler(
        "VOL-160",
        lambda payload: calls.append(payload) or {"value":"x"*128},
        handler_identity=record.spec.handler,
    )
    executor.set_budget(
        "VOL-160",
        Budget(max_attempts=1,max_cost_units=2,max_latency_ms=10),
        max_payload_bytes=128,
        max_result_bytes=32,
    )
    payload={"value":1}
    invocation=_invocation(record,"large-result",payload)

    with pytest.raises(DeferredExecutionError) as exc:
        executor.execute(invocation,payload)

    assert exc.value.receipt.error_type=="RuntimeError"
    assert calls==[{"value":1}]
    assert executor.receipt("large-result")==exc.value.receipt


def test_deferred_executor_rejects_invalid_byte_limits() -> None:
    registry=build_registry()
    _enable_volume(registry,"VOL-160")
    executor=DeferredExecutor(registry)

    with pytest.raises(ValueError,match="max_payload_bytes"):
        executor.set_budget(
            "VOL-160",
            Budget(max_attempts=1,max_cost_units=2,max_latency_ms=10),
            max_payload_bytes=0,
        )
    with pytest.raises(ValueError,match="max_result_bytes"):
        executor.set_budget(
            "VOL-160",
            Budget(max_attempts=1,max_cost_units=2,max_latency_ms=10),
            max_result_bytes=True,
        )

def test_deferred_executor_prepare_binds_current_authority() -> None:
    registry=build_registry()
    record=_enable_volume(registry,"VOL-160")
    executor=DeferredExecutor(registry)
    executor.register_handler(
        "VOL-160",
        lambda payload: {"ok":True},
        handler_identity=record.spec.handler,
    )
    executor.set_budget(
        "VOL-160",
        Budget(max_attempts=1,max_cost_units=2,max_latency_ms=10),
    )
    payload={"value":1}
    invocation=executor.prepare(
        "VOL-160",
        "prepared",
        payload,
        cost_units=1,
        latency_ms=1,
    )
    assert invocation.spec_digest==record.spec.digest
    assert invocation.authority_digest==DeferredExecutor.authority_digest(record)
    assert invocation.payload_digest==DeferredExecutor.digest_payload(payload)


def test_deferred_executor_success_replay_rechecks_current_authority() -> None:
    registry=build_registry()
    record=_enable_volume(registry,"VOL-160")
    calls=[]
    executor=DeferredExecutor(registry)
    executor.register_handler(
        "VOL-160",
        lambda payload: calls.append(payload) or {"ok":True},
        handler_identity=record.spec.handler,
    )
    executor.set_budget(
        "VOL-160",
        Budget(max_attempts=1,max_cost_units=2,max_latency_ms=10),
    )
    payload={"value":1}
    invocation=executor.prepare("VOL-160","stale-replay",payload)
    executor.execute(invocation,payload)

    record.transition("verified")

    with pytest.raises(PermissionError,match="authority digest drift"):
        executor.execute(invocation,payload)

    assert calls==[{"value":1}]


def test_deferred_executor_same_operation_cannot_execute_concurrently() -> None:
    registry=build_registry()
    record=_enable_volume(registry,"VOL-160")
    entered=threading.Event()
    release=threading.Event()
    calls=[]

    def handler(payload):
        calls.append(payload)
        entered.set()
        assert release.wait(timeout=5)
        return {"ok":True}

    executor=DeferredExecutor(registry)
    executor.register_handler(
        "VOL-160",
        handler,
        handler_identity=record.spec.handler,
    )
    executor.set_budget(
        "VOL-160",
        Budget(max_attempts=1,max_cost_units=2,max_latency_ms=10),
    )
    payload={"value":1}
    invocation=executor.prepare("VOL-160","race-op",payload)
    worker_errors=[]

    def run_first():
        try:
            executor.execute(invocation,payload)
        except BaseException as exc:
            worker_errors.append(exc)

    thread=threading.Thread(target=run_first)
    thread.start()
    assert entered.wait(timeout=5)

    with pytest.raises(RuntimeError,match="already in flight"):
        executor.execute(invocation,payload)

    release.set()
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert worker_errors==[]
    assert calls==[{"value":1}]


def test_deferred_executor_baseexception_is_terminal_and_not_replayed() -> None:
    registry=build_registry()
    record=_enable_volume(registry,"VOL-160")
    calls=[]

    class StopExecution(BaseException):
        pass

    def handler(payload):
        calls.append(payload)
        raise StopExecution()

    executor=DeferredExecutor(registry)
    executor.register_handler(
        "VOL-160",
        handler,
        handler_identity=record.spec.handler,
    )
    executor.set_budget(
        "VOL-160",
        Budget(max_attempts=1,max_cost_units=2,max_latency_ms=10),
    )
    payload={"value":1}
    invocation=executor.prepare("VOL-160","baseexception",payload)

    with pytest.raises(StopExecution):
        executor.execute(invocation,payload)

    receipt=executor.receipt("baseexception")
    assert receipt.status=="failed"
    assert receipt.error_type=="StopExecution"

    with pytest.raises(DeferredExecutionError,match="previously failed") as retry:
        executor.execute(invocation,payload)

    assert retry.value.receipt==receipt
    assert calls==[{"value":1}]


def test_deferred_invocation_bounds_operation_identity() -> None:
    registry=build_registry()
    record=_enable_volume(registry,"VOL-160")
    payload={"value":1}

    with pytest.raises(ValueError,match="at most 256"):
        DeferredInvocation(
            operation_id="x"*257,
            volume_id=record.spec.volume_id,
            spec_digest=record.spec.digest,
            authority_digest=DeferredExecutor.authority_digest(record),
            payload_digest=DeferredExecutor.digest_payload(payload),
        )

    with pytest.raises(ValueError,match="control characters"):
        DeferredInvocation(
            operation_id="bad\noperation",
            volume_id=record.spec.volume_id,
            spec_digest=record.spec.digest,
            authority_digest=DeferredExecutor.authority_digest(record),
            payload_digest=DeferredExecutor.digest_payload(payload),
        )


def test_execution_outcome_rejects_result_receipt_mismatch() -> None:
    registry=build_registry()
    record=_enable_volume(registry,"VOL-160")
    executor=DeferredExecutor(registry)
    executor.register_handler(
        "VOL-160",
        lambda payload: {"answer":42},
        handler_identity=record.spec.handler,
    )
    executor.set_budget(
        "VOL-160",
        Budget(max_attempts=1,max_cost_units=2,max_latency_ms=10),
    )
    payload={"value":1}
    outcome=executor.execute(
        executor.prepare("VOL-160","outcome-bound",payload),
        payload,
    )

    from skeleton.ai.runtime.deferred import ExecutionOutcome

    with pytest.raises(ValueError,match="result digest mismatch"):
        ExecutionOutcome(receipt=outcome.receipt,result={"answer":43})

def test_deferred_executor_snapshot_is_safe_during_inflight_execution() -> None:
    registry=build_registry()
    record=_enable_volume(registry,"VOL-160")
    entered=threading.Event()
    release=threading.Event()

    def handler(payload):
        entered.set()
        assert release.wait(timeout=5)
        return {"ok":True}

    executor=DeferredExecutor(registry)
    executor.register_handler(
        "VOL-160",
        handler,
        handler_identity=record.spec.handler,
    )
    executor.set_budget(
        "VOL-160",
        Budget(max_attempts=1,max_cost_units=2,max_latency_ms=10),
    )
    payload={"value":1}
    invocation=executor.prepare("VOL-160","snapshot-race",payload)
    errors=[]

    def run():
        try:
            executor.execute(invocation,payload)
        except BaseException as exc:
            errors.append(exc)

    thread=threading.Thread(target=run)
    thread.start()
    assert entered.wait(timeout=5)

    during=executor.snapshot()
    assert during["operations"]==[]

    release.set()
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert errors==[]

    after=executor.snapshot()
    assert [row["receipt"]["operation_id"] for row in after["operations"]]==[
        "snapshot-race"
    ]




def _durable_deferred_registry():
    registry = build_registry()
    record = registry.get("VOL-160")
    record.candidate(
        EvidenceReceipt(
            volume_id="VOL-160",
            head_sha=HEAD,
            artifact_digests=(HEX_A,),
            tests=("durable:candidate",),
            status="implementation_candidate",
            created_at="2026-10-04T00:00:00+00:00",
        )
    )
    record.verify(
        EvidenceReceipt(
            volume_id="VOL-160",
            head_sha=HEAD,
            artifact_digests=(HEX_A, HEX_B),
            tests=("durable:candidate", "durable:verified"),
            status="verified",
            created_at="2026-10-04T00:00:01+00:00",
        )
    )
    registry.enable("VOL-160")
    return registry, record


def _durable_deferred_executor(journal, handler):
    registry, record = _durable_deferred_registry()
    executor = DeferredExecutor(registry, journal=journal)
    executor.register_handler(
        "VOL-160",
        handler,
        handler_identity=record.spec.handler,
    )
    executor.set_budget(
        "VOL-160",
        Budget(max_attempts=1, max_cost_units=4, max_latency_ms=20),
    )
    return executor, record


def test_deferred_effect_journal_replays_success_without_second_effect(
    tmp_path,
) -> None:
    path = tmp_path / "deferred-effects.sqlite3"
    calls = []

    def handler(payload):
        calls.append(dict(payload))
        return {"answer": 42}

    first, _ = _durable_deferred_executor(
        SqliteDeferredExecutionJournal(path),
        handler,
    )
    payload = {"value": 1}
    invocation = first.prepare(
        "VOL-160",
        "durable-success",
        payload,
        cost_units=1,
        latency_ms=2,
    )
    initial = first.execute(invocation, payload)

    second_journal = SqliteDeferredExecutionJournal(path)
    second, _ = _durable_deferred_executor(second_journal, handler)
    replay_invocation = second.prepare(
        "VOL-160",
        "durable-success",
        payload,
        cost_units=1,
        latency_ms=2,
    )
    replay = second.execute(replay_invocation, payload)

    assert replay.receipt == initial.receipt
    assert replay.result == {"answer": 42}
    assert calls == [{"value": 1}]
    record = second_journal.load("durable-success")
    assert record is not None
    assert record.state == "succeeded"


def test_deferred_effect_journal_started_state_blocks_blind_retry(
    tmp_path,
) -> None:
    path = tmp_path / "deferred-started.sqlite3"
    journal = SqliteDeferredExecutionJournal(path)
    calls = []
    first, record = _durable_deferred_executor(
        journal,
        lambda payload: calls.append(dict(payload)) or {"ok": True},
    )
    payload = {"value": 1}
    invocation = first.prepare("VOL-160", "durable-started", payload)

    started, created = journal.record_started(
        operation_id=invocation.operation_id,
        fingerprint=invocation.fingerprint,
        invocation=invocation.as_dict(),
        handler_identity=record.spec.handler,
    )
    assert created
    assert started.state == "started"

    restarted, _ = _durable_deferred_executor(
        SqliteDeferredExecutionJournal(path),
        lambda payload: calls.append(dict(payload)) or {"ok": True},
    )
    with pytest.raises(
        DeferredExecutionPendingError,
        match="durable started state",
    ):
        restarted.execute(invocation, payload)

    assert calls == []


def test_deferred_effect_journal_explicit_unknown_fence_survives_restart(
    tmp_path,
) -> None:
    path = tmp_path / "deferred-fence.sqlite3"
    journal = SqliteDeferredExecutionJournal(path)
    calls = []
    first, record = _durable_deferred_executor(
        journal,
        lambda payload: calls.append(dict(payload)) or {"ok": True},
    )
    payload = {"value": 1}
    invocation = first.prepare("VOL-160", "durable-unknown", payload)
    journal.record_started(
        operation_id=invocation.operation_id,
        fingerprint=invocation.fingerprint,
        invocation=invocation.as_dict(),
        handler_identity=record.spec.handler,
    )

    recovery, _ = _durable_deferred_executor(
        SqliteDeferredExecutionJournal(path),
        lambda payload: calls.append(dict(payload)) or {"ok": True},
    )
    failure = recovery.fence_incomplete("durable-unknown")
    assert failure.error_type == "DeferredOutcomeUnknown"
    assert failure.status == "failed"

    restarted, _ = _durable_deferred_executor(
        SqliteDeferredExecutionJournal(path),
        lambda payload: calls.append(dict(payload)) or {"ok": True},
    )
    with pytest.raises(DeferredExecutionError, match="previously failed") as exc:
        restarted.execute(invocation, payload)

    assert exc.value.receipt == failure
    assert calls == []


def test_two_executors_never_run_same_durable_operation_concurrently(
    tmp_path,
) -> None:
    path = tmp_path / "deferred-race.sqlite3"
    entered = threading.Event()
    release = threading.Event()
    calls = []
    worker_errors = []

    def handler(payload):
        calls.append(dict(payload))
        entered.set()
        assert release.wait(timeout=5)
        return {"ok": True}

    first, _ = _durable_deferred_executor(
        SqliteDeferredExecutionJournal(path),
        handler,
    )
    second, _ = _durable_deferred_executor(
        SqliteDeferredExecutionJournal(path),
        handler,
    )
    payload = {"value": 1}
    invocation = first.prepare("VOL-160", "durable-race", payload)

    def run_first():
        try:
            first.execute(invocation, payload)
        except BaseException as exc:
            worker_errors.append(exc)

    thread = threading.Thread(target=run_first)
    thread.start()
    assert entered.wait(timeout=5)

    with pytest.raises(DeferredExecutionPendingError):
        second.execute(invocation, payload)

    release.set()
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert worker_errors == []
    assert calls == [{"value": 1}]

    replay = second.execute(invocation, payload)
    assert replay.result == {"ok": True}
    assert calls == [{"value": 1}]


def test_deferred_handler_failure_is_terminal_across_journal_restart(
    tmp_path,
) -> None:
    path = tmp_path / "deferred-failure.sqlite3"
    calls = []

    def handler(payload):
        calls.append(dict(payload))
        raise RuntimeError("provider private detail")

    first, _ = _durable_deferred_executor(
        SqliteDeferredExecutionJournal(path),
        handler,
    )
    payload = {"value": 1}
    invocation = first.prepare("VOL-160", "durable-failure", payload)

    with pytest.raises(DeferredExecutionError) as initial:
        first.execute(invocation, payload)

    restarted, _ = _durable_deferred_executor(
        SqliteDeferredExecutionJournal(path),
        handler,
    )
    with pytest.raises(DeferredExecutionError, match="previously failed") as replay:
        restarted.execute(invocation, payload)

    assert replay.value.receipt == initial.value.receipt
    assert calls == [{"value": 1}]


def test_success_commit_failure_leaves_durable_started_fence(
    tmp_path,
) -> None:
    path = tmp_path / "deferred-commit-failure.sqlite3"
    inner = SqliteDeferredExecutionJournal(path)
    calls = []

    class FailingTerminalJournal:
        def load(self, operation_id):
            return inner.load(operation_id)

        def records(self):
            return inner.records()

        def record_started(self, **kwargs):
            return inner.record_started(**kwargs)

        def record_terminal(self, **kwargs):
            raise RuntimeError("simulated terminal journal outage")

    def handler(payload):
        calls.append(dict(payload))
        return {"ok": True}

    first, _ = _durable_deferred_executor(
        FailingTerminalJournal(),
        handler,
    )
    payload = {"value": 1}
    invocation = first.prepare(
        "VOL-160",
        "durable-terminal-outage",
        payload,
    )

    with pytest.raises(
        DeferredExecutionError,
        match="could not be durably committed",
    ) as failed_commit:
        first.execute(invocation, payload)

    assert failed_commit.value.receipt.error_type == "DeferredJournalCommitError"
    durable = inner.load("durable-terminal-outage")
    assert durable is not None
    assert durable.state == "started"

    restarted, _ = _durable_deferred_executor(inner, handler)
    with pytest.raises(DeferredExecutionPendingError):
        restarted.execute(invocation, payload)

    assert calls == [{"value": 1}]


def test_deferred_effect_journal_rejects_resealed_result_tamper(
    tmp_path,
) -> None:
    path = tmp_path / "deferred-tamper.sqlite3"
    journal = SqliteDeferredExecutionJournal(path)
    first, _ = _durable_deferred_executor(
        journal,
        lambda payload: {"answer": 42},
    )
    payload = {"value": 1}
    invocation = first.prepare("VOL-160", "durable-tamper", payload)
    first.execute(invocation, payload)

    record = journal.load("durable-tamper")
    assert record is not None
    terminal = record.terminal
    assert terminal is not None
    terminal["result"] = {"answer": 43}
    material = record.digest_material()
    material["terminal"] = terminal
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            UPDATE deferred_execution_journal
            SET terminal_json = ?, record_digest = ?
            WHERE operation_id = ?
            """,
            (
                canonical_json(terminal),
                sha256_json(material),
                "durable-tamper",
            ),
        )

    restarted, _ = _durable_deferred_executor(
        SqliteDeferredExecutionJournal(path),
        lambda payload: {"answer": 42},
    )
    with pytest.raises(
        DeferredJournalConflict,
        match="result digest mismatch",
    ):
        restarted.execute(invocation, payload)


def test_deferred_effect_journal_rejects_operation_identity_collision(
    tmp_path,
) -> None:
    path = tmp_path / "deferred-collision.sqlite3"
    journal = SqliteDeferredExecutionJournal(path)
    calls = []
    first, record = _durable_deferred_executor(
        journal,
        lambda payload: calls.append(dict(payload)) or {"ok": True},
    )
    one = {"value": 1}
    two = {"value": 2}
    original = first.prepare("VOL-160", "durable-collision", one)
    journal.record_started(
        operation_id=original.operation_id,
        fingerprint=original.fingerprint,
        invocation=original.as_dict(),
        handler_identity=record.spec.handler,
    )

    restarted, _ = _durable_deferred_executor(
        SqliteDeferredExecutionJournal(path),
        lambda payload: calls.append(dict(payload)) or {"ok": True},
    )
    collision = restarted.prepare("VOL-160", "durable-collision", two)
    with pytest.raises(ValueError, match="operation identity collision"):
        restarted.execute(collision, two)

    assert calls == []


def test_recover_journal_hydrates_terminal_and_reports_pending(
    tmp_path,
) -> None:
    path = tmp_path / "deferred-recover.sqlite3"
    journal = SqliteDeferredExecutionJournal(path)
    first, record = _durable_deferred_executor(
        journal,
        lambda payload: {"ok": True},
    )
    payload = {"value": 1}
    complete = first.prepare("VOL-160", "durable-complete", payload)
    first.execute(complete, payload)

    pending = first.prepare("VOL-160", "durable-pending", payload)
    journal.record_started(
        operation_id=pending.operation_id,
        fingerprint=pending.fingerprint,
        invocation=pending.as_dict(),
        handler_identity=record.spec.handler,
    )

    restarted, _ = _durable_deferred_executor(
        SqliteDeferredExecutionJournal(path),
        lambda payload: {"ok": True},
    )
    unresolved = restarted.recover_journal()
    assert unresolved == ("durable-pending",)
    assert restarted.receipt("durable-complete").status == "succeeded"

    fenced = restarted.fence_incomplete("durable-pending")
    assert fenced.error_type == "DeferredOutcomeUnknown"
    assert restarted.receipt("durable-pending") == fenced


def test_durable_success_replay_still_requires_current_authority(
    tmp_path,
) -> None:
    path = tmp_path / "deferred-authority.sqlite3"
    journal = SqliteDeferredExecutionJournal(path)
    calls = []

    def handler(payload):
        calls.append(dict(payload))
        return {"ok": True}

    first, _ = _durable_deferred_executor(journal, handler)
    payload = {"value": 1}
    invocation = first.prepare("VOL-160", "durable-authority", payload)
    first.execute(invocation, payload)

    registry, record = _durable_deferred_registry()
    record.transition("verified")
    restarted = DeferredExecutor(
        registry,
        journal=SqliteDeferredExecutionJournal(path),
    )
    restarted.register_handler(
        "VOL-160",
        handler,
        handler_identity=record.spec.handler,
    )
    restarted.set_budget(
        "VOL-160",
        Budget(max_attempts=1, max_cost_units=4, max_latency_ms=20),
    )

    with pytest.raises(PermissionError, match="authority digest drift"):
        restarted.execute(invocation, payload)

    assert calls == [{"value": 1}]



def test_durable_journal_disables_restore_state_split_brain(tmp_path) -> None:
    path = tmp_path / "deferred-split-brain.sqlite3"
    plain, _ = _durable_deferred_executor(
        None,
        lambda payload: {"ok": True},
    )
    payload = {"value": 1}
    invocation = plain.prepare("VOL-160", "split-brain-source", payload)
    plain.execute(invocation, payload)
    checkpoint = plain.export_state()

    durable, _ = _durable_deferred_executor(
        SqliteDeferredExecutionJournal(path),
        lambda payload: {"ok": True},
    )
    with pytest.raises(
        RuntimeError,
        match="restore_state is disabled when a durable journal is configured",
    ):
        durable.restore_state(checkpoint)


def test_cannot_fence_locally_inflight_durable_operation(tmp_path) -> None:
    path = tmp_path / "deferred-local-inflight.sqlite3"
    entered = threading.Event()
    release = threading.Event()
    errors = []

    def handler(payload):
        entered.set()
        assert release.wait(timeout=5)
        return {"ok": True}

    executor, _ = _durable_deferred_executor(
        SqliteDeferredExecutionJournal(path),
        handler,
    )
    payload = {"value": 1}
    invocation = executor.prepare("VOL-160", "local-inflight", payload)

    def run():
        try:
            executor.execute(invocation, payload)
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=run)
    thread.start()
    assert entered.wait(timeout=5)

    with pytest.raises(RuntimeError, match="still in flight"):
        executor.fence_incomplete("local-inflight")

    release.set()
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert errors == []
    assert executor.receipt("local-inflight").status == "succeeded"


def test_durable_effect_journal_uses_wal_and_full_sync(tmp_path) -> None:
    path = tmp_path / "deferred-durability.sqlite3"
    SqliteDeferredExecutionJournal(path)

    with sqlite3.connect(path) as conn:
        mode = conn.execute("PRAGMA journal_mode").fetchone()
        assert mode is not None
        assert str(mode[0]).lower() == "wal"

    journal = SqliteDeferredExecutionJournal(path)
    with journal._connect() as conn:
        synchronous = conn.execute("PRAGMA synchronous").fetchone()
        assert synchronous is not None
        assert int(synchronous[0]) == 2



def test_effect_authority_is_checked_after_durable_start_before_handler(
    tmp_path,
) -> None:
    registry=build_registry()
    record=_enable_volume(registry,"VOL-160")
    journal=SqliteDeferredExecutionJournal(
        tmp_path / "effect-authority-order.sqlite3"
    )
    events=[]

    class Authority:
        def require_effect_authority(self, operation_id):
            durable=journal.load(operation_id)
            assert durable is not None
            assert durable.state=="started"
            events.append(("authority",operation_id))
            return object()

    executor=DeferredExecutor(
        registry,
        journal=journal,
        effect_authority=Authority(),
    )

    def handler(payload):
        events.append(("handler",payload["value"]))
        return {"ok":True}

    executor.register_handler(
        "VOL-160",
        handler,
        handler_identity=record.spec.handler,
        requires_effect_authority=True,
    )
    executor.set_budget(
        "VOL-160",
        Budget(max_attempts=1,max_cost_units=2,max_latency_ms=10),
    )
    payload={"value":1}
    invocation=executor.prepare("VOL-160","effect-order",payload)

    outcome=executor.execute(invocation,payload)

    assert outcome.result=={"ok":True}
    assert events==[
        ("authority","effect-order"),
        ("handler",1),
    ]


def test_effectful_handler_without_live_authority_fails_before_effect() -> None:
    registry=build_registry()
    record=_enable_volume(registry,"VOL-160")
    calls=[]
    executor=DeferredExecutor(registry)
    executor.register_handler(
        "VOL-160",
        lambda payload: calls.append(payload) or {"ok":True},
        handler_identity=record.spec.handler,
        requires_effect_authority=True,
    )
    executor.set_budget(
        "VOL-160",
        Budget(max_attempts=1,max_cost_units=2,max_latency_ms=10),
    )
    payload={"value":1}
    invocation=executor.prepare("VOL-160","missing-live-authority",payload)

    with pytest.raises(
        PermissionError,
        match="live effect authority is required",
    ):
        executor.execute(invocation,payload)

    assert calls==[]


def test_effect_authority_denial_is_terminal_and_never_dispatches(
    tmp_path,
) -> None:
    registry=build_registry()
    record=_enable_volume(registry,"VOL-160")
    journal=SqliteDeferredExecutionJournal(
        tmp_path / "effect-authority-denial.sqlite3"
    )
    authority_calls=[]
    handler_calls=[]

    class Authority:
        def require_effect_authority(self, operation_id):
            authority_calls.append(operation_id)
            raise RuntimeError("effect authority expired")

    executor=DeferredExecutor(
        registry,
        journal=journal,
        effect_authority=Authority(),
    )
    executor.register_handler(
        "VOL-160",
        lambda payload: handler_calls.append(payload) or {"ok":True},
        handler_identity=record.spec.handler,
        requires_effect_authority=True,
    )
    executor.set_budget(
        "VOL-160",
        Budget(max_attempts=1,max_cost_units=2,max_latency_ms=10),
    )
    payload={"value":1}
    invocation=executor.prepare("VOL-160","authority-denied",payload)

    with pytest.raises(DeferredExecutionError) as denied:
        executor.execute(invocation,payload)

    assert denied.value.receipt.error_type=="RuntimeError"
    assert authority_calls==["authority-denied"]
    assert handler_calls==[]
    durable=journal.load("authority-denied")
    assert durable is not None
    assert durable.state=="failed"

    with pytest.raises(DeferredExecutionError,match="previously failed") as retry:
        executor.execute(invocation,payload)

    assert retry.value.receipt==denied.value.receipt
    assert authority_calls==["authority-denied"]
    assert handler_calls==[]


def test_non_effectful_handler_does_not_consume_live_authority() -> None:
    registry=build_registry()
    record=_enable_volume(registry,"VOL-160")
    authority_calls=[]

    class Authority:
        def require_effect_authority(self, operation_id):
            authority_calls.append(operation_id)
            raise AssertionError("non-effectful handler must not request authority")

    executor=DeferredExecutor(
        registry,
        effect_authority=Authority(),
    )
    executor.register_handler(
        "VOL-160",
        lambda payload: {"ok":True},
        handler_identity=record.spec.handler,
    )
    executor.set_budget(
        "VOL-160",
        Budget(max_attempts=1,max_cost_units=2,max_latency_ms=10),
    )
    payload={"value":1}
    outcome=executor.execute(
        executor.prepare("VOL-160","pure-handler",payload),
        payload,
    )

    assert outcome.result=={"ok":True}
    assert authority_calls==[]


def test_effect_authority_constructor_rejects_invalid_provider() -> None:
    registry=build_registry()

    with pytest.raises(
        TypeError,
        match="require_effect_authority",
    ):
        DeferredExecutor(
            registry,
            effect_authority=object(),
        )
