from __future__ import annotations

from skeleton.eval.champion_registry import CandidateArtifact, ChampionRegistry
from skeleton.intelligence.routing_experiment import (
    RoutingPolicyArtifact,
    qualify_routing_challenger,
)


def _candidate(candidate_id: str, artifact_digest: str) -> CandidateArtifact:
    digest = "1" * 64
    return CandidateArtifact(
        candidate_id=candidate_id,
        version="v1",
        candidate_ref=f"routing/{candidate_id}",
        artifact_digest=artifact_digest,
        source_commit="a" * 40,
        experiment_manifest_digest=digest,
        benchmark_manifest_digest="2" * 64,
        benchmark_qualification_digest="3" * 64,
        reproducibility_bundle_digest="4" * 64,
    )


def _policy(policy_id: str = "learned-router-v1") -> RoutingPolicyArtifact:
    return RoutingPolicyArtifact(
        policy_id=policy_id,
        policy={"weights": {"quality": 0.7, "cost": 0.3}, "fallback": "incumbent"},
        training_evidence_digest="5" * 64,
    )


def test_registered_challenger_is_admitted_only_for_offline_evaluation() -> None:
    policy = _policy()
    champion = _candidate("champion", "6" * 64)
    challenger = _candidate("challenger", policy.artifact_digest)
    registry = ChampionRegistry(
        registry_id="routing",
        candidates=(champion, challenger),
        initial_champion_digest=champion.candidate_digest,
    )

    decision = qualify_routing_challenger(
        registry=registry,
        challenger_digest=challenger.candidate_digest,
        policy_artifact=policy,
    )

    assert decision.accepted_for_offline_evaluation is True
    assert decision.production_authority is False
    assert decision.champion_digest == champion.candidate_digest


def test_unregistered_challenger_fails_closed() -> None:
    policy = _policy()
    champion = _candidate("champion", "6" * 64)
    outsider = _candidate("outsider", policy.artifact_digest)
    registry = ChampionRegistry(
        registry_id="routing",
        candidates=(champion,),
        initial_champion_digest=champion.candidate_digest,
    )
    decision = qualify_routing_challenger(
        registry=registry,
        challenger_digest=outsider.candidate_digest,
        policy_artifact=policy,
    )
    assert decision.accepted_for_offline_evaluation is False
    assert decision.reasons == ("challenger-not-registered",)


def test_current_champion_cannot_masquerade_as_challenger() -> None:
    policy = _policy()
    champion = _candidate("champion", policy.artifact_digest)
    registry = ChampionRegistry(
        registry_id="routing",
        candidates=(champion,),
        initial_champion_digest=champion.candidate_digest,
    )
    decision = qualify_routing_challenger(
        registry=registry,
        challenger_digest=champion.candidate_digest,
        policy_artifact=policy,
    )
    assert decision.accepted_for_offline_evaluation is False
    assert decision.reasons == ("challenger-is-current-champion",)


def test_policy_artifact_identity_must_match_registered_candidate() -> None:
    policy = _policy()
    champion = _candidate("champion", "6" * 64)
    challenger = _candidate("challenger", "7" * 64)
    registry = ChampionRegistry(
        registry_id="routing",
        candidates=(champion, challenger),
        initial_champion_digest=champion.candidate_digest,
    )
    decision = qualify_routing_challenger(
        registry=registry,
        challenger_digest=challenger.candidate_digest,
        policy_artifact=policy,
    )
    assert decision.accepted_for_offline_evaluation is False
    assert decision.reasons == ("policy-artifact-digest-mismatch",)


def test_decision_identity_is_deterministic_and_has_no_authority_escalation() -> None:
    policy = _policy()
    champion = _candidate("champion", "6" * 64)
    challenger = _candidate("challenger", policy.artifact_digest)
    registry = ChampionRegistry(
        registry_id="routing",
        candidates=(champion, challenger),
        initial_champion_digest=champion.candidate_digest,
    )
    first = qualify_routing_challenger(
        registry=registry,
        challenger_digest=challenger.candidate_digest,
        policy_artifact=policy,
    )
    second = qualify_routing_challenger(
        registry=registry,
        challenger_digest=challenger.candidate_digest,
        policy_artifact=policy,
    )
    assert first.decision_digest == second.decision_digest
    assert first.payload()["production_authority"] is False
