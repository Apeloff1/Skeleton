from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.agents.blast_radius import BlastRadiusDecision, ImpactClass
from skeleton.contracts.canonical import EvidenceRef
from skeleton.eval.champion_registry import CandidateArtifact, ChampionRegistry
from skeleton.eval.experiment_registry import (
    ExperimentBudget,
    ExperimentEligibility,
    ExperimentManifest,
    ExperimentMetric,
    MetricDirection,
    TrafficMode,
)
from skeleton.eval.shadow_traffic import (
    ShadowTrafficError,
    ShadowTrafficObservation,
    qualify_shadow_traffic,
)


def _experiment(
    *,
    traffic_mode: TrafficMode = TrafficMode.SHADOW,
    max_fraction: float = 0.10,
    allowed_data_classes: tuple[str, ...] = ("public",),
    tenant_ids: tuple[str, ...] = (),
) -> ExperimentManifest:
    return ExperimentManifest(
        experiment_id="shadow-experiment",
        hypothesis="Shadow challenger improves quality without interference.",
        owner="team-eval",
        source_commit="a" * 40,
        environment_id="shadow-env",
        candidate_ref="challenger-v2",
        eligibility=ExperimentEligibility(
            traffic_mode=traffic_mode,
            max_traffic_fraction=max_fraction,
            allowed_data_classes=allowed_data_classes,
            tenant_ids=tenant_ids,
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
    candidate_ref: str,
    artifact_char: str,
    *,
    experiment_digest: str,
) -> CandidateArtifact:
    return CandidateArtifact(
        candidate_id=candidate_id,
        version="v1",
        candidate_ref=candidate_ref,
        artifact_digest=artifact_char * 64,
        source_commit="a" * 40,
        experiment_manifest_digest=experiment_digest,
        benchmark_manifest_digest="b" * 64,
        benchmark_qualification_digest="c" * 64,
        reproducibility_bundle_digest="d" * 64,
    )


def _registry(
    experiment: ExperimentManifest,
) -> tuple[ChampionRegistry, CandidateArtifact, CandidateArtifact]:
    champion = _candidate(
        "champion",
        "champion-v1",
        "1",
        experiment_digest="e" * 64,
    )
    challenger = _candidate(
        "challenger",
        experiment.candidate_ref,
        "2",
        experiment_digest=experiment.manifest_digest,
    )
    return (
        ChampionRegistry(
            registry_id="shadow-registry",
            candidates=(champion, challenger),
            initial_champion_digest=champion.candidate_digest,
        ),
        champion,
        challenger,
    )


def _observation(
    experiment: ExperimentManifest,
    registry: ChampionRegistry,
    challenger: CandidateArtifact,
    **overrides: object,
) -> ShadowTrafficObservation:
    values: dict[str, object] = {
        "operation_id": "operation-1",
        "execution_id": "execution-1",
        "agent_id": "agent-1",
        "tenant_id": "tenant-a",
        "data_class": "public",
        "request_digest": "3" * 64,
        "experiment_manifest_digest": experiment.manifest_digest,
        "challenger_digest": challenger.candidate_digest,
        "champion_digest_before": registry.current_champion_digest,
        "champion_digest_after": registry.current_champion_digest,
        "registry_digest_before": registry.registry_digest,
        "registry_digest_after": registry.registry_digest,
        "production_response_before_digest": "4" * 64,
        "production_response_after_digest": "4" * 64,
        "shadow_response_digest": "5" * 64,
        "sampled_fraction": 0.05,
        "persistent_write_count": 0,
        "external_side_effect_count": 0,
        "shadow_selected_for_production": False,
        "evaluator_id": "verifier:shadow-independent",
        "evaluator_digest": "6" * 64,
        "independent": True,
        "evidence_refs": (
            EvidenceRef(
                source="ci://shadow/evaluation",
                digest="7" * 64,
                category="shadow_evaluation",
            ),
        ),
    }
    values.update(overrides)
    return ShadowTrafficObservation(**values)


def _blast(
    observation: ShadowTrafficObservation,
    *,
    accepted: bool = True,
    impact: ImpactClass = ImpactClass.LOW,
    **overrides: object,
) -> BlastRadiusDecision:
    values: dict[str, object] = {
        "accepted": accepted,
        "impact": impact,
        "reasons": () if accepted else ("forced-rejection",),
        "operation_id": observation.operation_id,
        "execution_id": observation.execution_id,
        "agent_id": observation.agent_id,
        "action_digest": observation.shadow_action_digest,
        "authority_digest": "8" * 64,
        "profile_digest": "9" * 64,
        "alignment_digest": "a" * 64,
        "policy_digest": "b" * 64,
        "risk_evaluation_digest": None,
        "human_receipt_digest": None,
    }
    values.update(overrides)
    return BlastRadiusDecision(**values)


def _chain(**observation_overrides: object):
    experiment = _experiment()
    registry, champion, challenger = _registry(experiment)
    observation = _observation(
        experiment,
        registry,
        challenger,
        **observation_overrides,
    )
    blast = _blast(observation)
    return experiment, registry, champion, challenger, observation, blast


def test_clean_shadow_observation_is_accepted() -> None:
    experiment, registry, _, challenger, observation, blast = _chain()

    decision = qualify_shadow_traffic(
        experiment=experiment,
        registry=registry,
        challenger=challenger,
        observation=observation,
        blast_radius=blast,
    )

    assert decision.accepted is True
    assert decision.reasons == ()
    assert decision.registry_digest == registry.registry_digest
    assert decision.champion_digest == registry.current_champion_digest
    assert decision.challenger_digest == challenger.candidate_digest
    assert decision.shadow_action_digest == observation.shadow_action_digest
    evidence = decision.accepted_evidence_ref()
    assert evidence.category == "shadow_traffic_isolation"
    assert evidence.digest == decision.decision_digest


def test_experiment_must_be_shadow_mode() -> None:
    experiment = _experiment(
        traffic_mode=TrafficMode.OFFLINE,
        max_fraction=0.0,
    )
    registry, _, challenger = _registry(experiment)
    observation = _observation(
        experiment,
        registry,
        challenger,
    )
    blast = _blast(observation)

    decision = qualify_shadow_traffic(
        experiment=experiment,
        registry=registry,
        challenger=challenger,
        observation=observation,
        blast_radius=blast,
    )
    assert decision.accepted is False
    assert "experiment-not-shadow-mode" in decision.reasons


def test_fraction_data_class_and_tenant_scope_fail_closed() -> None:
    experiment = _experiment(
        allowed_data_classes=("public", "internal"),
        tenant_ids=("tenant-a",),
    )
    registry, _, challenger = _registry(experiment)
    observation = _observation(
        experiment,
        registry,
        challenger,
        sampled_fraction=0.20,
        data_class="secret",
        tenant_id="tenant-b",
    )
    decision = qualify_shadow_traffic(
        experiment=experiment,
        registry=registry,
        challenger=challenger,
        observation=observation,
        blast_radius=_blast(observation),
    )

    assert decision.accepted is False
    assert "shadow-traffic-fraction-exceeded" in decision.reasons
    assert "shadow-data-class-not-allowed" in decision.reasons
    assert "shadow-tenant-not-eligible" in decision.reasons


def test_challenger_must_be_registered_and_match_experiment() -> None:
    experiment, registry, _, challenger, observation, blast = _chain()
    substitute = _candidate(
        "other",
        "other-v1",
        "f",
        experiment_digest=experiment.manifest_digest,
    )

    decision = qualify_shadow_traffic(
        experiment=experiment,
        registry=registry,
        challenger=substitute,
        observation=observation,
        blast_radius=blast,
    )

    assert decision.accepted is False
    assert "challenger-substitution" in decision.reasons
    assert "challenger-ref-mismatch" in decision.reasons
    assert "observation-challenger-digest-mismatch" in decision.reasons


def test_current_champion_cannot_be_shadow_challenger() -> None:
    experiment = replace(
        _experiment(),
        candidate_ref="champion-v1",
    )
    incumbent = _candidate(
        "champion",
        experiment.candidate_ref,
        "1",
        experiment_digest=experiment.manifest_digest,
    )
    other = _candidate(
        "challenger",
        "challenger-v2",
        "2",
        experiment_digest=experiment.manifest_digest,
    )
    registry = ChampionRegistry(
        registry_id="shadow-registry",
        candidates=(incumbent, other),
        initial_champion_digest=incumbent.candidate_digest,
    )
    observation = _observation(
        experiment,
        registry,
        incumbent,
    )

    decision = qualify_shadow_traffic(
        experiment=experiment,
        registry=registry,
        challenger=incumbent,
        observation=observation,
        blast_radius=_blast(observation),
    )
    assert decision.accepted is False
    assert "shadow-candidate-is-current-champion" in decision.reasons


@pytest.mark.parametrize(
    ("overrides", "reason"),
    (
        (
            {"registry_digest_after": "0" * 64},
            "registry-after-digest-mismatch",
        ),
        (
            {"champion_digest_after": "0" * 64},
            "champion-after-digest-mismatch",
        ),
        (
            {"persistent_write_count": 1},
            "shadow-persistent-write-detected",
        ),
        (
            {"external_side_effect_count": 1},
            "shadow-external-side-effect-detected",
        ),
        (
            {"shadow_selected_for_production": True},
            "shadow-output-selected-for-production",
        ),
        (
            {"production_response_after_digest": "0" * 64},
            "production-response-mutated",
        ),
        (
            {"independent": False},
            "shadow-evaluator-not-independent",
        ),
        (
            {"evaluator_id": "agent-1"},
            "shadow-evaluator-is-agent",
        ),
    ),
)
def test_shadow_non_interference_mutations_block(
    overrides: dict[str, object],
    reason: str,
) -> None:
    experiment, registry, _, challenger, observation, _ = _chain(
        **overrides
    )
    decision = qualify_shadow_traffic(
        experiment=experiment,
        registry=registry,
        challenger=challenger,
        observation=observation,
        blast_radius=_blast(observation),
    )

    assert decision.accepted is False
    assert reason in decision.reasons


def test_registry_and_champion_mutation_are_named_explicitly() -> None:
    experiment, registry, _, challenger, observation, _ = _chain(
        registry_digest_after="0" * 64,
        champion_digest_after="1" * 64,
    )
    decision = qualify_shadow_traffic(
        experiment=experiment,
        registry=registry,
        challenger=challenger,
        observation=observation,
        blast_radius=_blast(observation),
    )

    assert "shadow-mutated-registry" in decision.reasons
    assert "shadow-mutated-champion" in decision.reasons


@pytest.mark.parametrize(
    ("blast_overrides", "reason"),
    (
        (
            {"accepted": False, "reasons": ("rejected",)},
            "blast-radius-rejected",
        ),
        (
            {"action_digest": "0" * 64},
            "blast-action-digest-mismatch",
        ),
        (
            {"operation_id": "other-operation"},
            "blast-operation-mismatch",
        ),
        (
            {"execution_id": "other-execution"},
            "blast-execution-mismatch",
        ),
        (
            {"agent_id": "other-agent"},
            "blast-agent-mismatch",
        ),
        (
            {"impact": ImpactClass.HIGH},
            "shadow-blast-radius-too-high",
        ),
        (
            {"impact": ImpactClass.CRITICAL},
            "shadow-blast-radius-too-high",
        ),
    ),
)
def test_auto05_binding_failures_block(
    blast_overrides: dict[str, object],
    reason: str,
) -> None:
    experiment, registry, _, challenger, observation, _ = _chain()
    blast = _blast(observation, **blast_overrides)

    decision = qualify_shadow_traffic(
        experiment=experiment,
        registry=registry,
        challenger=challenger,
        observation=observation,
        blast_radius=blast,
    )

    assert decision.accepted is False
    assert reason in decision.reasons


def test_moderate_blast_radius_can_remain_shadow_safe() -> None:
    experiment, registry, _, challenger, observation, _ = _chain()
    blast = _blast(observation, impact=ImpactClass.MODERATE)

    decision = qualify_shadow_traffic(
        experiment=experiment,
        registry=registry,
        challenger=challenger,
        observation=observation,
        blast_radius=blast,
    )
    assert decision.accepted is True


def test_rejected_shadow_decision_cannot_be_promotion_evidence() -> None:
    experiment, registry, _, challenger, observation, _ = _chain(
        shadow_selected_for_production=True,
    )
    decision = qualify_shadow_traffic(
        experiment=experiment,
        registry=registry,
        challenger=challenger,
        observation=observation,
        blast_radius=_blast(observation),
    )

    assert decision.accepted is False
    with pytest.raises(ShadowTrafficError, match="cannot become promotion"):
        decision.accepted_evidence_ref()


def test_evidence_order_is_canonical() -> None:
    experiment, registry, _, challenger, _, _ = _chain()
    first = EvidenceRef(
        source="ci://shadow/a",
        digest="1" * 64,
        category="shadow_evaluation",
    )
    second = EvidenceRef(
        source="ci://shadow/b",
        digest="2" * 64,
        category="shadow_evaluation",
    )
    left = _observation(
        experiment,
        registry,
        challenger,
        evidence_refs=(second, first, second),
    )
    right = _observation(
        experiment,
        registry,
        challenger,
        evidence_refs=(first, second),
    )

    assert left.evidence_refs == right.evidence_refs
    assert left.observation_digest == right.observation_digest
