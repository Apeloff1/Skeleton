from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from skeleton.ai.runtime.deferred import build_registry, volume_ids
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

