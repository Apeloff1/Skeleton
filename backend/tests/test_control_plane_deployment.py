from dataclasses import replace

from core.control_plane_deployment import (
    evaluate_control_plane_deployment,
    verify_control_plane_deployment_preflight,
)


def _assurance():
    return {"posture": "healthy", "hard_failures": 0, "warnings": 0, "attestation_sha256": "a" * 64}


def _trust(*, finality=True, required=True):
    return {
        "integrity_healthy": True,
        "finality_satisfied": finality,
        "deploy_ready": finality if required else True,
        "policy": {
            "configured": True, "configured_independence_groups": 3,
            "required_groups": 3, "max_age_seconds": 3600,
            "quorum_capable": True, "finality_required": required,
        },
        "gossip": {"split_views": 0, "rollbacks": 0, "healthy": True},
        "witnesses": {"equivocations": 0, "healthy": True},
        "current_head": {"current_tree_size": 8, "current_root_sha256": "b" * 64, "finalized": finality},
    }


class StablePlane:
    def __init__(self, *, finality=True):
        self.finality = finality

    def system_root(self):
        return {"root_sha256": "c" * 64}

    def assurance_report(self):
        return _assurance()

    def epistemic_finality(self):
        return _trust(finality=self.finality)


class FlappingPlane(StablePlane):
    def __init__(self):
        super().__init__(); self.counter = 0

    def system_root(self):
        self.counter += 1
        return {"root_sha256": f"{self.counter:064x}"[-64:]}


def test_stable_finalized_control_plane_can_authorize_deployment():
    report = evaluate_control_plane_deployment(StablePlane(), evaluated_at="2026-09-14T16:30:00+00:00")
    assert report.stable is True
    assert report.allowed is True
    assert report.attempts == 1
    assert report.root_before_sha256 == report.root_after_sha256
    assert verify_control_plane_deployment_preflight(report) is True


def test_stable_state_still_blocks_when_required_finality_is_missing():
    report = evaluate_control_plane_deployment(StablePlane(finality=False), evaluated_at="2026-09-14T16:30:00+00:00")
    assert report.stable is True
    assert report.allowed is False
    assert "finality.current-head" in {x.id for x in report.report.blockers}


def test_continuously_mutating_system_root_blocks_even_if_subsystems_report_healthy():
    report = evaluate_control_plane_deployment(FlappingPlane(), max_attempts=3,
                                               evaluated_at="2026-09-14T16:30:00+00:00")
    assert report.stable is False
    assert report.allowed is False
    assert report.attempts == 3
    assert report.root_before_sha256 != report.root_after_sha256
    assert "changed during 3 consecutive" in report.unstable_reason
    assert verify_control_plane_deployment_preflight(report) is True


def test_control_plane_preflight_attestation_detects_mutation():
    report = evaluate_control_plane_deployment(StablePlane(), evaluated_at="2026-09-14T16:30:00+00:00")
    assert verify_control_plane_deployment_preflight(report) is True
    assert verify_control_plane_deployment_preflight(replace(report, allowed=False)) is False
