from __future__ import annotations

import pytest

from skeleton.ai.runtime.deferred.reliability_release import (
    ReleaseQualification,
    ReleaseRequirement,
    ReleaseWaiver,
)


HEX_A = "a" * 64


def _matrix() -> ReleaseQualification:
    return ReleaseQualification(
        (
            ReleaseRequirement("tests", release_classes=("default", "high-risk")),
            ReleaseRequirement("security", release_classes=("default", "high-risk")),
            ReleaseRequirement("adversarial", release_classes=("high-risk",)),
        )
    )


def test_release_class_selects_exact_required_gate_set() -> None:
    matrix = _matrix()
    default = matrix.decide(
        release_id="r1",
        release_class="default",
        conclusions={"tests": "success", "security": "success"},
        now=10,
    )
    assert default.qualified
    assert default.blockers == ()

    high_risk = matrix.decide(
        release_id="r1",
        release_class="high-risk",
        conclusions={"tests": "success", "security": "success"},
        now=10,
    )
    assert not high_risk.qualified
    assert high_risk.blockers == ("adversarial:missing",)


@pytest.mark.parametrize("conclusion", ["cancelled", "failure", "skipped", "pending", "", None])
def test_non_success_and_missing_required_gate_fail_closed(conclusion: object) -> None:
    matrix = ReleaseQualification((ReleaseRequirement("security"),))
    decision = matrix.decide(
        release_id="r1",
        release_class="default",
        conclusions={"security": conclusion},
        now=10,
    )
    assert not decision.qualified


def test_waiver_is_class_scoped_evidence_bound_and_expires() -> None:
    matrix = ReleaseQualification((ReleaseRequirement("security"),))
    waiver = ReleaseWaiver(
        gate_id="security",
        release_class="default",
        evidence_digest=HEX_A,
        approver="release-authority",
        expires_at=20,
    )
    active = matrix.decide(
        release_id="r1",
        release_class="default",
        conclusions={"security": "failure"},
        now=19,
        waivers=(waiver,),
    )
    assert active.qualified
    assert active.waived_gates == ("security",)

    expired = matrix.decide(
        release_id="r1",
        release_class="default",
        conclusions={"security": "failure"},
        now=20,
        waivers=(waiver,),
    )
    assert not expired.qualified
    assert expired.blockers == ("security:failure",)


def test_waiver_cannot_cross_release_class_or_target_unknown_gate() -> None:
    matrix = _matrix()
    with pytest.raises(ValueError, match="cross-class"):
        matrix.decide(
            release_id="r1",
            release_class="high-risk",
            conclusions={"tests": "success", "security": "success", "adversarial": "failure"},
            now=1,
            waivers=(ReleaseWaiver("adversarial", "default", HEX_A, "authority", 10),),
        )

    with pytest.raises(ValueError, match="non-required"):
        ReleaseQualification((ReleaseRequirement("tests"),)).decide(
            release_id="r1",
            release_class="default",
            conclusions={"tests": "success"},
            now=1,
            waivers=(ReleaseWaiver("security", "default", HEX_A, "authority", 10),),
        )


def test_qualification_digest_binds_release_inputs_and_waiver_evidence() -> None:
    matrix = ReleaseQualification((ReleaseRequirement("security"),))
    first = matrix.decide(
        release_id="r1",
        release_class="default",
        conclusions={"security": "failure"},
        now=1,
        waivers=(ReleaseWaiver("security", "default", HEX_A, "authority", 10),),
    )
    second = matrix.decide(
        release_id="r2",
        release_class="default",
        conclusions={"security": "failure"},
        now=1,
        waivers=(ReleaseWaiver("security", "default", HEX_A, "authority", 10),),
    )
    assert first.input_digest != second.input_digest


def test_matrix_rejects_undeclared_release_class() -> None:
    with pytest.raises(ValueError, match="no release requirements"):
        _matrix().decide(
            release_id="r1",
            release_class="emergency",
            conclusions={},
            now=1,
        )
