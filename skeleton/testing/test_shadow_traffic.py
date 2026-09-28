from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.agents.blast_radius import (
    ActionRiskProfile,
    BlastRadiusDecision,
    ImpactClass,
    ReversibilityClass,
)
from skeleton.contracts.canonical import EvidenceRef
from skeleton.eval.champion_registry import (
    CandidateArtifact,
    ChampionRegistry,
)
from skeleton.eval.experiment_registry import (
    ExperimentBudget,
    ExperimentEligibility,
    ExperimentManifest,
    ExperimentMetric,
    ExperimentRegistryError,
    MetricDirection,
    TrafficMode,
)
from skeleton.eval.shadow_traffic import (
    PairedShadowObservation,
    ShadowInputReceipt,
    ShadowPolicy,
    ShadowSourceAuthority,
    ShadowTrafficError,
    qualify_shadow_traffic,
)


def _experiment(
    *,
    candidate_ref: str = "challenger-v2",
    traffic_mode: TrafficMode = TrafficMode.SHADOW,
    max_fraction: float = 0.10,
    allowed_data_classes: tuple[str, ...] = ("public",),
    tenant_ids: tuple[str, ...] = ("tenant-a",),
    external_side_effects_allowed: bool = False,
) -> ExperimentManifest:
    return ExperimentManifest(
        experiment_id="shadow-experiment",
        hypothesis="Shadow challenger improves quality without interference.",
        owner="team-eval",
        source_commit="a" * 40,
        environment_id="shadow-env",
        candidate_ref=candidate_ref,
        eligibility=ExperimentEligibility(
            traffic_mode=traffic_mode,
            max_traffic_fraction=max_fraction,
            allowed_data_classes=allowed_data_classes,
            tenant_ids=tenant_ids,
            external_side_effects_allowed=external_side_effects_allowed,
        ),
        budget=ExperimentBudget(
            max_samples=1000,
            max_tokens=100000,
            max_cost_units=100.0,
            max_wall_time_s=3600.0,
        ),
        metrics=(
            ExperimentMetric(
                metric_id="quality",
                direction=MetricDirection.MAXIMIZE,
                minimum_samples=100,
                source="independent-evaluator",
            ),
        ),
    )


def _candidate(
    candidate_id: str,
    version: str,
    *,
    experiment_digest: str,
    parent: str | None = None,
) -> CandidateArtifact:
    fill = "1" if candidate_id == "champion" else "2"
    return CandidateArtifact(
        candidate_id=candidate_id,
        version=version,
        candidate_ref=f"{candidate_id}-{version}",
        artifact_digest=fill * 64,
        source_commit=fill * 40,
        experiment_manifest_digest=experiment_digest,
        benchmark_manifest_digest="4" * 64,
        benchmark_qualification_digest="5" * 64,
        reproducibility_bundle_digest="6" * 64,
        parent_candidate_digest=parent,
        tags=("shadow",),
    )


def _registry(
    experiment: ExperimentManifest,
) -> tuple[ChampionRegistry, CandidateArtifact, CandidateArtifact]:
    champion = _candidate(
        "champion",
        "v1",
        experiment_digest="3" * 64,
    )
    challenger = _candidate(
        "challenger",
        "v2",
        experiment_digest=experiment.manifest_digest,
        parent=champion.candidate_digest,
    )
    return (
        ChampionRegistry(
            registry_id="registry-1",
            candidates=(champion, challenger),
            initial_champion_digest=champion.candidate_digest,
        ),
        champion,
        challenger,
    )


def _source(
    *,
    tenant_id: str = "tenant-a",
) -> ShadowSourceAuthority:
    return ShadowSourceAuthority(
        operation_id="operation-1",
        tenant_id=tenant_id,
        operation_projection_digest="7" * 64,
        projection_decision_digest="8" * 64,
        operation_version=5,
        cursor_sequence=5,
        evidence=EvidenceRef(
            source="p1:prod-02:streaming-projection",
            digest="8" * 64,
            category="streaming_projection_authority",
        ),
    )


def _input(
    *,
    sensitive: bool = False,
    data_class: str = "public",
) -> ShadowInputReceipt:
    return ShadowInputReceipt(
        original_input_digest="9" * 64,
        redacted_input_digest=("a" * 64 if sensitive else "9" * 64),
        redaction_policy_digest="b" * 64,
        data_class=data_class,
        sensitive_input=sensitive,
        removed_classes=(("credential",) if sensitive else ()),
    )


def _profile(**overrides: object) -> ActionRiskProfile:
    values: dict[str, object] = {
        "operation_id": "operation-1",
        "execution_id": "shadow-execution-1",
        "agent_id": "shadow-agent",
        "action_digest": "c" * 64,
        "authority_digest": "d" * 64,
        "affected_tenants": 1,
        "affected_resources": 1,
        "reversibility": ReversibilityClass.REVERSIBLE,
        "writes_persistent_state": False,
        "externally_observable": False,
        "privileged": False,
        "destructive": False,
        "sensitive_data": False,
    }
    values.update(overrides)
    return ActionRiskProfile(**values)


def _blast(
    profile: ActionRiskProfile,
    **overrides: object,
) -> BlastRadiusDecision:
    values: dict[str, object] = {
        "accepted": True,
        "impact": ImpactClass.LOW,
        "reasons": (),
        "operation_id": profile.operation_id,
        "execution_id": profile.execution_id,
        "agent_id": profile.agent_id,
        "action_digest": profile.action_digest,
        "authority_digest": profile.authority_digest,
        "profile_digest": profile.digest,
        "alignment_digest": "e" * 64,
        "policy_digest": "f" * 64,
        "risk_evaluation_digest": None,
        "human_receipt_digest": None,
    }
    values.update(overrides)
    return BlastRadiusDecision(**values)


def _observation(
    candidate: CandidateArtifact,
    source: ShadowSourceAuthority,
    shadow_input: ShadowInputReceipt,
    registry: ChampionRegistry,
    **overrides: object,
) -> PairedShadowObservation:
    values: dict[str, object] = {
        "experiment_manifest_digest": candidate.experiment_manifest_digest,
        "candidate_digest": candidate.candidate_digest,
        "source_authority_digest": source.digest,
        "shadow_input_digest": shadow_input.digest,
        "champion_output_digest": "1" * 64,
        "challenger_output_digest": "2" * 64,
        "comparator_id": "paired-comparator",
        "comparator_digest": "3" * 64,
        "champion_latency_ms": 20.0,
        "challenger_latency_ms": 18.0,
        "registry_digest_before": registry.registry_digest,
        "registry_digest_after": registry.registry_digest,
        "champion_digest_before": registry.current_champion_digest,
        "champion_digest_after": registry.current_champion_digest,
        "production_response_before_digest": "4" * 64,
        "production_response_after_digest": "4" * 64,
        "evaluator_id": "verifier:shadow-independent",
        "evaluator_digest": "5" * 64,
        "independent": True,
        "persistent_write_count": 0,
        "external_side_effect_count": 0,
        "shadow_selected_for_production": False,
        "user_visible_output": False,
        "canonical_write_count": 0,
    }
    values.update(overrides)
    return PairedShadowObservation(**values)


def _decision(
    *,
    experiment: ExperimentManifest | None = None,
    candidate: CandidateArtifact | None = None,
    registry: ChampionRegistry | None = None,
    source: ShadowSourceAuthority | None = None,
    shadow_input: ShadowInputReceipt | None = None,
    profile: ActionRiskProfile | None = None,
    blast: BlastRadiusDecision | None = None,
    observation: PairedShadowObservation | None = None,
    requested_fraction: float = 0.05,
):
    experiment = experiment or _experiment()
    default_registry, _, challenger = _registry(experiment)
    registry = registry or default_registry
    candidate = candidate or challenger
    source = source or _source()
    shadow_input = shadow_input or _input()
    profile = profile or _profile()
    blast = blast or _blast(profile)
    observation = observation or _observation(
        candidate,
        source,
        shadow_input,
        registry,
    )
    return qualify_shadow_traffic(
        experiment=experiment,
        registry=registry,
        candidate=candidate,
        source=source,
        shadow_input=shadow_input,
        action_profile=profile,
        blast_radius=blast,
        observation=observation,
        policy=ShadowPolicy(
            policy_id="shadow-policy",
            version=1,
            max_traffic_fraction=0.10,
        ),
        requested_fraction=requested_fraction,
    )


def test_clean_challenger_shadow_run_qualifies() -> None:
    experiment = _experiment()
    decision = _decision(experiment=experiment)

    assert decision.accepted is True
    assert decision.reasons == ()
    assert decision.experiment_manifest_digest == experiment.manifest_digest
    evidence = decision.accepted_evidence_ref()
    assert evidence.category == "shadow_traffic_qualification"
    assert evidence.digest == decision.decision_digest


def test_current_champion_cannot_be_shadow_challenger() -> None:
    experiment = _experiment()
    registry, champion, _ = _registry(experiment)
    source = _source()
    shadow_input = _input()
    profile = _profile()
    decision = _decision(
        experiment=experiment,
        candidate=champion,
        registry=registry,
        source=source,
        shadow_input=shadow_input,
        profile=profile,
        blast=_blast(profile),
        observation=_observation(
            champion,
            source,
            shadow_input,
            registry,
        ),
    )

    assert decision.accepted is False
    assert "shadow-candidate-is-current-champion" in decision.reasons
    assert "experiment-candidate-ref-mismatch" in decision.reasons


def test_unregistered_candidate_is_rejected() -> None:
    experiment = _experiment(candidate_ref="outsider-v9")
    registry, _, _ = _registry(experiment)
    outsider = _candidate(
        "outsider",
        "v9",
        experiment_digest=experiment.manifest_digest,
    )
    source = _source()
    shadow_input = _input()
    profile = _profile()

    decision = _decision(
        experiment=experiment,
        candidate=outsider,
        registry=registry,
        source=source,
        shadow_input=shadow_input,
        profile=profile,
        blast=_blast(profile),
        observation=_observation(
            outsider,
            source,
            shadow_input,
            registry,
        ),
    )

    assert decision.accepted is False
    assert "candidate-not-registered" in decision.reasons


def test_sensitive_input_requires_real_redaction() -> None:
    with pytest.raises(
        ShadowTrafficError,
        match="must change under redaction",
    ):
        ShadowInputReceipt(
            original_input_digest="9" * 64,
            redacted_input_digest="9" * 64,
            redaction_policy_digest="b" * 64,
            data_class="public",
            sensitive_input=True,
            removed_classes=("credential",),
        )


def test_experiment_must_be_shadow_mode_and_side_effect_free() -> None:
    offline = _experiment(
        traffic_mode=TrafficMode.OFFLINE,
        max_fraction=0.0,
    )
    decision = _decision(experiment=offline)
    assert decision.accepted is False
    assert "experiment-not-shadow-mode" in decision.reasons

    with pytest.raises(
        ExperimentRegistryError,
        match="may not authorize external side effects",
    ):
        _experiment(external_side_effects_allowed=True)


def test_candidate_must_bind_exact_experiment() -> None:
    experiment = _experiment()
    registry, _, challenger = _registry(experiment)
    substituted = replace(
        challenger,
        experiment_manifest_digest="0" * 64,
    )
    source = _source()
    shadow_input = _input()
    profile = _profile()
    observation = _observation(
        substituted,
        source,
        shadow_input,
        registry,
    )

    decision = _decision(
        experiment=experiment,
        candidate=substituted,
        registry=registry,
        source=source,
        shadow_input=shadow_input,
        profile=profile,
        blast=_blast(profile),
        observation=observation,
    )

    assert decision.accepted is False
    assert "candidate-experiment-digest-mismatch" in decision.reasons


def test_fraction_data_class_and_tenant_eligibility_fail_closed() -> None:
    experiment = _experiment(
        max_fraction=0.04,
        allowed_data_classes=("public",),
        tenant_ids=("tenant-a",),
    )

    too_much = _decision(
        experiment=experiment,
        requested_fraction=0.05,
    )
    assert "shadow-fraction-exceeds-experiment" in too_much.reasons

    wrong_class = _decision(
        experiment=experiment,
        shadow_input=_input(data_class="internal"),
    )
    assert "shadow-data-class-not-eligible" in wrong_class.reasons

    wrong_tenant = _decision(
        experiment=experiment,
        source=_source(tenant_id="tenant-b"),
    )
    assert "shadow-tenant-not-eligible" in wrong_tenant.reasons


@pytest.mark.parametrize(
    ("overrides", "reason"),
    (
        ({"writes_persistent_state": True}, "persistent-write-requested"),
        ({"externally_observable": True}, "external-side-effect-requested"),
        ({"privileged": True}, "privileged-action-requested"),
        ({"destructive": True}, "destructive-action-requested"),
        ({"sensitive_data": True}, "sensitive-data-action-requested"),
        (
            {
                "reversibility": ReversibilityClass.RECOVERABLE,
                "recovery_plan_digest": "4" * 64,
                "rollback_test_digest": "5" * 64,
            },
            "shadow-action-not-reversible",
        ),
    ),
)
def test_shadow_side_effect_profiles_fail_closed(
    overrides: dict[str, object],
    reason: str,
) -> None:
    profile = _profile(**overrides)
    decision = _decision(profile=profile, blast=_blast(profile))

    assert decision.accepted is False
    assert reason in decision.reasons


def test_blast_radius_rejection_and_substitution_block() -> None:
    profile = _profile()
    rejected = _blast(
        profile,
        accepted=False,
        reasons=("forced-rejection",),
    )
    decision = _decision(profile=profile, blast=rejected)
    assert decision.accepted is False
    assert "blast-radius-rejected" in decision.reasons

    substituted = _blast(profile, action_digest="0" * 64)
    decision = _decision(profile=profile, blast=substituted)
    assert decision.accepted is False
    assert "blast-action-digest-mismatch" in decision.reasons


def test_source_and_input_substitution_block() -> None:
    experiment = _experiment()
    registry, _, challenger = _registry(experiment)
    source = _source()
    shadow_input = _input()
    profile = _profile()
    observation = _observation(
        challenger,
        source,
        shadow_input,
        registry,
        source_authority_digest="0" * 64,
        shadow_input_digest="1" * 64,
    )
    decision = _decision(
        experiment=experiment,
        registry=registry,
        candidate=challenger,
        source=source,
        shadow_input=shadow_input,
        profile=profile,
        blast=_blast(profile),
        observation=observation,
    )

    assert decision.accepted is False
    assert "observation-source-mismatch" in decision.reasons
    assert "observation-input-mismatch" in decision.reasons


def test_champion_and_registry_mutation_block() -> None:
    experiment = _experiment()
    registry, _, challenger = _registry(experiment)
    source = _source()
    shadow_input = _input()
    observation = _observation(
        challenger,
        source,
        shadow_input,
        registry,
        registry_digest_after="0" * 64,
        champion_digest_after="1" * 64,
    )

    decision = _decision(
        experiment=experiment,
        registry=registry,
        candidate=challenger,
        source=source,
        shadow_input=shadow_input,
        observation=observation,
    )

    assert decision.accepted is False
    assert "registry-after-digest-mismatch" in decision.reasons
    assert "shadow-mutated-registry" in decision.reasons
    assert "champion-after-digest-mismatch" in decision.reasons
    assert "shadow-mutated-champion" in decision.reasons


def test_production_response_and_side_effect_mutation_block() -> None:
    experiment = _experiment()
    registry, _, challenger = _registry(experiment)
    source = _source()
    shadow_input = _input()
    observation = _observation(
        challenger,
        source,
        shadow_input,
        registry,
        production_response_after_digest="0" * 64,
        persistent_write_count=1,
        external_side_effect_count=1,
        shadow_selected_for_production=True,
        user_visible_output=True,
    )

    decision = _decision(
        experiment=experiment,
        registry=registry,
        candidate=challenger,
        source=source,
        shadow_input=shadow_input,
        observation=observation,
    )

    assert decision.accepted is False
    assert "production-response-mutated" in decision.reasons
    assert "shadow-persistent-write-detected" in decision.reasons
    assert "shadow-external-side-effect-detected" in decision.reasons
    assert "shadow-output-selected-for-production" in decision.reasons
    assert "shadow-output-user-visible" in decision.reasons


def test_evaluator_must_be_independent_and_not_shadow_agent() -> None:
    experiment = _experiment()
    registry, _, challenger = _registry(experiment)
    source = _source()
    shadow_input = _input()

    non_independent = _observation(
        challenger,
        source,
        shadow_input,
        registry,
        independent=False,
    )
    decision = _decision(
        experiment=experiment,
        registry=registry,
        candidate=challenger,
        source=source,
        shadow_input=shadow_input,
        observation=non_independent,
    )
    assert "shadow-evaluator-not-independent" in decision.reasons

    same_actor = _observation(
        challenger,
        source,
        shadow_input,
        registry,
        evaluator_id="shadow-agent",
    )
    decision = _decision(
        experiment=experiment,
        registry=registry,
        candidate=challenger,
        source=source,
        shadow_input=shadow_input,
        observation=same_actor,
    )
    assert "shadow-evaluator-is-agent" in decision.reasons


def test_canonical_write_count_is_structurally_forbidden() -> None:
    experiment = _experiment()
    registry, _, challenger = _registry(experiment)
    with pytest.raises(ShadowTrafficError, match="cannot write canonical"):
        _observation(
            challenger,
            _source(),
            _input(),
            registry,
            canonical_write_count=1,
        )


def test_policy_cannot_enable_shadow_side_effects() -> None:
    with pytest.raises(ShadowTrafficError, match="must remain false"):
        ShadowPolicy(
            policy_id="unsafe-shadow",
            version=1,
            allow_persistent_writes=True,
        )


def test_source_requires_exact_prod02_evidence_category() -> None:
    with pytest.raises(ShadowTrafficError, match="PROD-02"):
        replace(
            _source(),
            evidence=EvidenceRef(
                source="wrong://source",
                digest="8" * 64,
                category="workspace_projection_authority",
            ),
        )


def test_rejected_shadow_run_cannot_materialize_evidence() -> None:
    decision = _decision(requested_fraction=0.20)

    assert decision.accepted is False
    with pytest.raises(ShadowTrafficError, match="cannot become promotion"):
        decision.accepted_evidence_ref()
