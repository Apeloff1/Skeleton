from __future__ import annotations

import pytest

from skeleton.ai.runtime.deferred.operations_assurance import (
    CanaryPromotionPolicy,
    CanaryQualityVector,
    ChangeClassification,
    ContractTemplate,
    ContractTemplateRegistry,
    FaultDefinition,
    FaultLibrary,
    FeatureFlagSetPolicy,
    FlagCombinationConstraint,
    FlagDescriptor,
    FormalCandidateSelection,
    FuzzTarget,
    FuzzTargetRegistry,
    GeneratorRegistry,
    GeneratorSpec,
    MergeReadinessBinding,
    OperationsAssuranceError,
    RecoveryDrillPlan,
    RecoveryDrillScheduler,
    RecoveryFinding,
    RollbackProof,
    SimulationAdapterProfile,
    assess_formal_conformance,
    qualify_rollback,
    select_simulation_adapter,
)


A = "a" * 64
B = "b" * 64
C = "c" * 64
D = "d" * 64
HEAD = "e" * 40


def test_fault_library_binds_every_fault_to_runbook_and_duration_limit() -> None:
    library = FaultLibrary(
        (
            FaultDefinition(
                "retrieval-latency",
                "retrieval",
                "latency",
                5,
                "runbook://retrieval/latency",
                "slo-breach",
            ),
            FaultDefinition(
                "cache-loss",
                "cache",
                "availability",
                3,
                "runbook://cache/rebuild",
                "error-budget-breach",
            ),
        )
    )

    plan = library.plan(
        "campaign-1",
        ("retrieval-latency", "cache-loss"),
        requested_total_duration_seconds=8,
    )

    assert len(plan.fault_digests) == 2
    assert plan.runbook_refs == (
        "runbook://cache/rebuild",
        "runbook://retrieval/latency",
    )
    assert plan.external_side_effects_authorized is False
    assert len(plan.digest) == 64


def test_fault_library_fails_closed_on_unknown_or_excessive_fault_plan() -> None:
    library = FaultLibrary(
        (
            FaultDefinition(
                "latency",
                "retrieval",
                "latency",
                5,
                "runbook://retrieval",
                "abort",
            ),
        )
    )
    with pytest.raises(OperationsAssuranceError, match="unknown fault"):
        library.plan(
            "campaign",
            ("missing",),
            requested_total_duration_seconds=1,
        )
    with pytest.raises(OperationsAssuranceError, match="exceeds"):
        library.plan(
            "campaign",
            ("latency",),
            requested_total_duration_seconds=6,
        )


def test_recovery_drill_scheduler_binds_findings_to_risk_ledger() -> None:
    scheduler = RecoveryDrillScheduler()
    plan = RecoveryDrillPlan(
        "restore-primary",
        "staging",
        1_000,
        ("runbook://restore",),
        30_000,
        1_000,
        ("dns-cutover",),
    )
    first = scheduler.schedule(plan)
    second = scheduler.schedule(plan)
    assert first == second == plan.digest

    scheduler.attach_finding(
        RecoveryFinding(
            "finding-1",
            "restore-primary",
            "high",
            "RISK-RESTORE-DNS",
            "resilience",
        )
    )
    scheduler.attach_finding(
        RecoveryFinding(
            "finding-2",
            "restore-primary",
            "medium",
            "RISK-RESOLVED",
            "resilience",
            resolved=True,
        )
    )
    assert scheduler.unresolved_risk_refs() == ("RISK-RESTORE-DNS",)


def test_recovery_finding_cannot_reference_unscheduled_drill() -> None:
    scheduler = RecoveryDrillScheduler()
    with pytest.raises(OperationsAssuranceError, match="unscheduled"):
        scheduler.attach_finding(
            RecoveryFinding(
                "finding",
                "missing",
                "high",
                "RISK-X",
                "owner",
            )
        )


def test_merge_readiness_requires_exact_success_for_every_declared_gate() -> None:
    binding = MergeReadinessBinding(("tests", "security", "artifact"))
    decision = binding.assess(
        release_id="r1",
        qualification_digest=A,
        exact_head_sha=HEAD,
        conclusions={
            "tests": "success",
            "security": "success",
            "artifact": "success",
        },
    )
    assert decision.qualified is True
    assert decision.blockers == ()
    assert decision.merge_authority is False
    assert len(decision.digest) == 64


@pytest.mark.parametrize("bad", ("failure", "cancelled", "skipped", "neutral"))
def test_merge_readiness_rejects_non_success_gate_state(bad: str) -> None:
    binding = MergeReadinessBinding(("tests", "security"))
    decision = binding.assess(
        release_id="r1",
        qualification_digest=A,
        exact_head_sha=HEAD,
        conclusions={"tests": "success", "security": bad},
    )
    assert decision.qualified is False
    assert decision.blockers == (f"security:{bad}",)


def test_merge_readiness_rejects_missing_and_undeclared_gates() -> None:
    binding = MergeReadinessBinding(("tests", "security"))
    decision = binding.assess(
        release_id="r1",
        qualification_digest=A,
        exact_head_sha=HEAD,
        conclusions={"tests": "success", "extra": "success"},
    )
    assert decision.qualified is False
    assert decision.blockers == ("security:missing", "undeclared:extra")


def canary_policy() -> CanaryPromotionPolicy:
    return CanaryPromotionPolicy(
        min_samples=100,
        min_quality_ppm=950_000,
        min_error_budget_remaining_ppm=100_000,
        max_cost_ratio_ppm=900_000,
    )


def test_canary_quality_vector_promotes_only_as_candidate() -> None:
    decision = canary_policy().decide(
        CanaryQualityVector(
            100,
            970_000,
            500_000,
            800_000,
            True,
        )
    )
    assert decision.decision == "promote-candidate"
    assert decision.blockers == ()
    assert decision.production_authority is False


def test_canary_security_or_error_budget_failure_forces_rollback() -> None:
    decision = canary_policy().decide(
        CanaryQualityVector(
            100,
            970_000,
            50_000,
            800_000,
            False,
        )
    )
    assert decision.decision == "rollback"
    assert decision.blockers == (
        "error-budget-exhausted",
        "security-gate-failed",
    )


def test_canary_insufficient_sample_or_cost_excess_holds_without_false_promotion() -> None:
    decision = canary_policy().decide(
        CanaryQualityVector(
            10,
            970_000,
            500_000,
            950_000,
            True,
        )
    )
    assert decision.decision == "hold"
    assert decision.blockers == ("cost-ratio-exceeded", "insufficient-samples")


def flag_policy() -> FeatureFlagSetPolicy:
    return FeatureFlagSetPolicy(
        (
            FlagDescriptor("new-router", "runtime", "tenant", False, 10_000),
            FlagDescriptor(
                "security-bypass",
                "security",
                "global",
                False,
                10_000,
                security_sensitive=True,
            ),
            FlagDescriptor("alt-cache", "runtime", "tenant", False, 10_000),
        ),
        (
            FlagCombinationConstraint(
                "router-cache-mutual-exclusion",
                ("new-router", "alt-cache"),
                1,
            ),
        ),
    )


def test_flag_policy_accepts_nonexpired_bounded_combination() -> None:
    decision = flag_policy().evaluate(
        {
            "new-router": True,
            "security-bypass": False,
            "alt-cache": False,
        },
        now_ms=5_000,
    )
    assert decision.allowed is True
    assert decision.blockers == ()


def test_flag_policy_blocks_expired_security_override_and_bad_combination() -> None:
    decision = flag_policy().evaluate(
        {
            "new-router": True,
            "security-bypass": True,
            "alt-cache": True,
        },
        now_ms=10_000,
    )
    assert decision.allowed is False
    assert decision.blockers == (
        "alt-cache:expired-enabled",
        "new-router:expired-enabled",
        "router-cache-mutual-exclusion:combination-violation",
        "security-bypass:expired-enabled",
        "security-bypass:security-sensitive-override",
    )


def test_flag_policy_requires_exact_registered_flag_set() -> None:
    with pytest.raises(OperationsAssuranceError, match="exact registered"):
        flag_policy().evaluate(
            {"new-router": False},
            now_ms=1,
        )


def reversible_change(*, external: bool = False) -> ChangeClassification:
    return ChangeClassification(
        "change-1",
        "schema-compatible-release",
        durable_data_change=True,
        external_effects=external,
        backward_read_compatible=True,
        reversible=True,
    )


def proof(
    classification: ChangeClassification,
    *,
    external_digest: str | None = None,
) -> RollbackProof:
    return RollbackProof(
        classification.digest,
        A,
        B,
        C,
        external_digest,
    )


def test_rollback_requires_proof_bound_to_exact_change_classification() -> None:
    change = reversible_change()
    missing = qualify_rollback(change, None)
    assert missing.allowed is False
    assert missing.reason_code == "rollback-proof-missing"

    qualified = qualify_rollback(change, proof(change))
    assert qualified.allowed is True
    assert qualified.reason_code == "rollback-proof-qualified"


def test_rollback_external_effects_require_reconciliation_evidence() -> None:
    change = reversible_change(external=True)
    denied = qualify_rollback(change, proof(change))
    assert denied.allowed is False
    assert denied.reason_code == "external-effect-reconciliation-missing"

    qualified = qualify_rollback(change, proof(change, external_digest=D))
    assert qualified.allowed is True


def test_incompatible_durable_change_cannot_claim_reversibility() -> None:
    with pytest.raises(OperationsAssuranceError, match="cannot claim"):
        ChangeClassification(
            "bad",
            "schema-break",
            durable_data_change=True,
            external_effects=False,
            backward_read_compatible=False,
            reversible=True,
        )


def test_forward_fix_only_change_never_qualifies_for_rollback() -> None:
    change = ChangeClassification(
        "irreversible",
        "external-migration",
        durable_data_change=True,
        external_effects=True,
        backward_read_compatible=False,
        reversible=False,
    )
    decision = qualify_rollback(change, None)
    assert decision.allowed is False
    assert decision.reason_code == "change-classified-forward-fix-only"


def test_contract_template_registry_binds_contract_command_files_and_values() -> None:
    registry = ContractTemplateRegistry(
        (
            ContractTemplate(
                "provider-adapter",
                "provider.contract.v1",
                "skeleton-dev generate-provider",
                ("skeleton/ai/providers/{name}.py", "skeleton/testing/test_{name}.py"),
                ("name", "owner"),
            ),
        )
    )
    receipt = registry.render_receipt(
        "provider-adapter",
        {"name": "example", "owner": "runtime"},
    )
    assert receipt.contract_id == "provider.contract.v1"
    assert receipt.command_id == "skeleton-dev generate-provider"
    assert receipt.mutating_authority is False
    assert len(receipt.template_digest) == 64
    assert len(receipt.value_digest) == 64


def test_contract_template_requires_exact_placeholder_set() -> None:
    registry = ContractTemplateRegistry(
        (
            ContractTemplate(
                "t",
                "c",
                "cmd",
                ("file.py",),
                ("name",),
            ),
        )
    )
    with pytest.raises(OperationsAssuranceError, match="exactly match"):
        registry.render_receipt("t", {"name": "x", "extra": "y"})


def test_simulation_adapter_switch_is_explicit_and_never_production_evidence() -> None:
    profile = SimulationAdapterProfile(
        "mail",
        "mail.simulated",
        "mail.production",
        "simulation-fixture",
    )
    receipt = select_simulation_adapter(profile, simulation_mode=True)
    assert receipt.selected_adapter_id == "mail.simulated"
    assert receipt.simulated is True
    assert receipt.production_eligible is False
    assert set(receipt.evidence_labels) == {
        "simulation-fixture",
        "non-production",
        "simulated-effect",
    }


def test_simulation_adapter_switch_refuses_implicit_or_production_mode() -> None:
    profile = SimulationAdapterProfile("mail", "mail.simulated", "mail.production")
    with pytest.raises(OperationsAssuranceError, match="explicit simulation"):
        select_simulation_adapter(profile, simulation_mode=False)
    with pytest.raises(OperationsAssuranceError, match="must differ"):
        SimulationAdapterProfile("mail", "same", "same")


def fuzz_registry() -> FuzzTargetRegistry:
    return FuzzTargetRegistry(
        (
            FuzzTarget(
                "provider-envelope",
                "provider-envelope.v1",
                "p0",
                "skeleton.providers.contract.validate",
                "skeleton/testing/test_provider_envelope_regressions.py",
            ),
            FuzzTarget(
                "optional-config",
                "config.optional.v1",
                "p2",
                "skeleton.config.validate",
                "skeleton/testing/test_config_regressions.py",
            ),
        )
    )


def test_fuzz_registry_materializes_p0_inventory() -> None:
    targets = fuzz_registry().p0_targets()
    assert tuple(item.target_id for item in targets) == ("provider-envelope",)


def test_fuzz_reproducer_is_bound_to_regression_target() -> None:
    binding = fuzz_registry().promote_reproducer(
        "provider-envelope",
        reproducer_digest=A,
    )
    assert binding.promoted is True
    assert (
        binding.regression_test_target
        == "skeleton/testing/test_provider_envelope_regressions.py"
    )
    assert len(binding.target_digest) == 64


def test_fuzz_registry_rejects_unknown_target() -> None:
    with pytest.raises(OperationsAssuranceError, match="unknown fuzz target"):
        fuzz_registry().promote_reproducer("missing", reproducer_digest=A)


def generator_registry() -> GeneratorRegistry:
    return GeneratorRegistry(
        (
            GeneratorSpec(
                "ledger-amount",
                "balance.nonnegative",
                "Ledger",
                "signed-int64",
                0,
                10_000,
            ),
        ),
        invariant_ids=("balance.nonnegative",),
    )


def test_generator_registry_binds_named_generator_to_invariant_and_seed_domain() -> None:
    binding = generator_registry().bind("ledger-amount", seed=73)
    assert binding.invariant_id == "balance.nonnegative"
    assert binding.seed == 73
    assert len(binding.generator_digest) == 64


def test_generator_registry_rejects_unknown_invariant_and_out_of_domain_seed() -> None:
    with pytest.raises(OperationsAssuranceError, match="unknown invariant"):
        GeneratorRegistry(
            (
                GeneratorSpec(
                    "bad",
                    "missing.invariant",
                    "Ledger",
                    "int",
                    0,
                    10,
                ),
            ),
            invariant_ids=("known",),
        )

    with pytest.raises(OperationsAssuranceError, match="outside declared"):
        generator_registry().bind("ledger-amount", seed=10_001)


def test_formal_candidate_selection_preserves_ranked_identity_digest_pairing() -> None:
    selection = FormalCandidateSelection(
        ("candidate-high", "candidate-next"),
        (A, B),
        HEAD,
    )
    assert selection.candidate_ids == ("candidate-high", "candidate-next")
    assert selection.candidate_digests == (A, B)
    assert len(selection.digest) == 64


def test_formal_conformance_requires_exact_head_and_exact_test_inventory() -> None:
    selection = FormalCandidateSelection(("candidate",), (A,), HEAD)

    with pytest.raises(OperationsAssuranceError, match="selected exact head"):
        assess_formal_conformance(
            selection,
            handoff_digest=B,
            test_targets=("test::runtime",),
            exact_head_sha="f" * 40,
            test_results={"test::runtime": "success"},
        )

    with pytest.raises(OperationsAssuranceError, match="exact test inventory"):
        assess_formal_conformance(
            selection,
            handoff_digest=B,
            test_targets=("test::runtime",),
            exact_head_sha=HEAD,
            test_results={},
        )


def test_formal_conformance_fails_closed_on_non_success_regression() -> None:
    selection = FormalCandidateSelection(("candidate",), (A,), HEAD)
    decision = assess_formal_conformance(
        selection,
        handoff_digest=B,
        test_targets=("test::runtime", "test::recovery"),
        exact_head_sha=HEAD,
        test_results={
            "test::runtime": "success",
            "test::recovery": "failure",
        },
    )
    assert decision.conformant is False
    assert decision.blockers == ("test::recovery:failure",)
    assert decision.completion_authority is False


def test_formal_conformance_green_is_still_evidence_only() -> None:
    selection = FormalCandidateSelection(("candidate",), (A,), HEAD)
    decision = assess_formal_conformance(
        selection,
        handoff_digest=B,
        test_targets=("test::runtime",),
        exact_head_sha=HEAD,
        test_results={"test::runtime": "success"},
    )
    assert decision.conformant is True
    assert decision.blockers == ()
    assert decision.completion_authority is False
