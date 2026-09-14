from dataclasses import replace

from core.deployment_preflight import evaluate_deployment_preflight, verify_deployment_preflight


def _assurance(*, posture="healthy", hard_failures=0, warnings=0):
    return {
        "posture": posture,
        "hard_failures": hard_failures,
        "warnings": warnings,
        "attestation_sha256": "a" * 64,
    }


def _trust(*, integrity=True, finality=False, required=False, quorum_capable=True,
           split_views=0, rollbacks=0, equivocations=0, tree_size=4):
    return {
        "integrity_healthy": integrity,
        "finality_satisfied": finality,
        "deploy_ready": integrity and (finality if required else True),
        "policy": {
            "configured": quorum_capable,
            "configured_independence_groups": 3 if quorum_capable else 0,
            "required_groups": 3,
            "max_age_seconds": 3600,
            "quorum_capable": quorum_capable,
            "finality_required": required,
        },
        "gossip": {"split_views": split_views, "rollbacks": rollbacks, "healthy": not (split_views or rollbacks)},
        "witnesses": {"equivocations": equivocations, "healthy": equivocations == 0},
        "current_head": {"current_tree_size": tree_size, "current_root_sha256": "b" * 64, "finalized": finality},
    }


def test_nonrequired_finality_is_visible_but_does_not_block_deploy():
    report = evaluate_deployment_preflight(
        assurance=_assurance(), trust=_trust(finality=False, required=False), system_root_sha256="c" * 64,
    )
    assert report.allowed is True
    assert report.posture == "degraded"
    assert {x.id for x in report.warnings} == {"finality.current-head"}
    assert verify_deployment_preflight(report) is True


def test_required_finality_blocks_until_current_head_is_finalized():
    report = evaluate_deployment_preflight(
        assurance=_assurance(), trust=_trust(finality=False, required=True), system_root_sha256="c" * 64,
    )
    assert report.allowed is False
    assert report.posture == "blocked"
    assert "finality.current-head" in {x.id for x in report.blockers}

    ready = evaluate_deployment_preflight(
        assurance=_assurance(), trust=_trust(finality=True, required=True), system_root_sha256="c" * 64,
    )
    assert ready.allowed is True
    assert ready.posture == "ready"


def test_split_view_and_rollback_block_even_if_summary_claims_integrity():
    split = evaluate_deployment_preflight(
        assurance=_assurance(), trust=_trust(integrity=True, split_views=1), system_root_sha256="d" * 64,
    )
    assert split.allowed is False
    assert "trust.split-view" in {x.id for x in split.blockers}

    rollback = evaluate_deployment_preflight(
        assurance=_assurance(), trust=_trust(integrity=True, rollbacks=1), system_root_sha256="d" * 64,
    )
    assert rollback.allowed is False
    assert "trust.rollback" in {x.id for x in rollback.blockers}


def test_witness_equivocation_and_assurance_failure_are_independent_blockers():
    report = evaluate_deployment_preflight(
        assurance=_assurance(posture="blocked", hard_failures=2),
        trust=_trust(integrity=False, equivocations=1), system_root_sha256="e" * 64,
    )
    blocker_ids = {x.id for x in report.blockers}
    assert {"assurance.blocked", "trust.integrity", "trust.witness-equivocation"} <= blocker_ids
    assert report.allowed is False


def test_preflight_attestation_detects_mutation():
    report = evaluate_deployment_preflight(
        assurance=_assurance(), trust=_trust(finality=True), system_root_sha256="f" * 64,
    )
    assert verify_deployment_preflight(report) is True
    assert verify_deployment_preflight(replace(report, allowed=False)) is False
