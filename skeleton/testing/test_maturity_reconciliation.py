from __future__ import annotations

from copy import deepcopy

import pytest

from skeleton.contracts.maturity_reconciliation import (
    MaturityReconciliationError,
    reconcile_volume,
)


POLICY = {
    "specified": {"required_nonempty_fields": []},
    "scaffolded": {
        "required_nonempty_fields": [
            "requirements",
            "capabilities",
            "contracts",
            "risks",
            "gaps",
        ]
    },
    "implemented": {
        "required_nonempty_fields": [
            "requirements",
            "capabilities",
            "contracts",
            "implementation_paths",
            "tests",
            "risks",
            "gaps",
        ]
    },
    "integrated": {
        "required_nonempty_fields": [
            "requirements",
            "capabilities",
            "contracts",
            "implementation_paths",
            "tests",
            "evaluations",
            "risks",
            "gaps",
        ]
    },
    "verified": {
        "required_nonempty_fields": [
            "requirements",
            "capabilities",
            "contracts",
            "implementation_paths",
            "tests",
            "evaluations",
            "evidence",
            "risks",
            "gaps",
        ]
    },
    "hardened": {
        "required_nonempty_fields": [
            "requirements",
            "capabilities",
            "contracts",
            "implementation_paths",
            "tests",
            "evaluations",
            "evidence",
            "risks",
        ]
    },
    "production": {
        "required_nonempty_fields": [
            "requirements",
            "capabilities",
            "contracts",
            "implementation_paths",
            "tests",
            "evaluations",
            "evidence",
            "risks",
        ]
    },
}


def _volume(**overrides: object) -> dict:
    value = {
        "key": "VOL-999",
        "status": "specified",
        "implementation_status": "unverified",
        "accountability_id": "ACC-VOL-999",
        "requirements": ["requirement"],
        "capabilities": ["capability"],
        "contracts": ["Contract"],
        "implementation_paths": ["skeleton/example.py"],
        "tests": ["tests/test_example.py"],
        "evaluations": ["eval:integration"],
        "evidence": ["evidence:acceptance"],
        "risks": ["risk"],
        "gaps": ["gap"],
    }
    value.update(overrides)
    return value


def _signoff(signed: bool) -> dict:
    return {"signed": signed}


def _accountability(**overrides: object) -> dict:
    value = {
        "id": "ACC-VOL-999",
        "status": "unverified",
        "implementation_signoff": _signoff(False),
        "verification_signoff": _signoff(False),
        "evidence": [],
    }
    value.update(overrides)
    return value


def _evaluation(decision, state: str):
    return next(item for item in decision.evaluations if item.state == state)


def test_unsigned_volume_can_only_become_scaffolded() -> None:
    decision = reconcile_volume(
        _volume(),
        _accountability(),
        POLICY,
        target_floor="verified",
    )

    assert decision.highest_eligible_status == "scaffolded"
    assert decision.promotion_candidate == "scaffolded"
    assert decision.target_floor_eligible is False
    assert any(
        "implementation accountability is unsigned" in blocker
        for blocker in _evaluation(decision, "implemented").blockers
    )


def test_planned_test_never_counts_as_materialized_implementation() -> None:
    decision = reconcile_volume(
        _volume(tests=["planned:tests/test_example.py"]),
        _accountability(
            status="implemented",
            implementation_signoff=_signoff(True),
        ),
        POLICY,
        target_floor="implemented",
    )

    implemented = _evaluation(decision, "implemented")
    assert implemented.eligible is False
    assert any(
        "tests must contain materialized references" in blocker
        for blocker in implemented.blockers
    )


def test_signed_implementation_can_become_implemented() -> None:
    decision = reconcile_volume(
        _volume(),
        _accountability(
            status="implemented",
            implementation_signoff=_signoff(True),
        ),
        POLICY,
        target_floor="implemented",
    )

    assert _evaluation(decision, "implemented").eligible is True
    assert decision.highest_eligible_status == "implemented"
    assert decision.promotion_candidate == "implemented"
    assert decision.implementation_status_candidate == "implemented"
    assert decision.accountability_maturity_status == "implemented"
    assert decision.target_floor_eligible is True


def test_integrated_requires_accountability_at_integrated() -> None:
    decision = reconcile_volume(
        _volume(),
        _accountability(
            status="implemented",
            implementation_signoff=_signoff(True),
        ),
        POLICY,
        target_floor="integrated",
    )

    integrated = _evaluation(decision, "integrated")
    assert integrated.eligible is False
    assert any(
        "accountability status is below integrated" in blocker
        for blocker in integrated.blockers
    )


def test_verified_requires_independent_signoff_and_materialized_evidence() -> None:
    unsigned = reconcile_volume(
        _volume(),
        _accountability(
            status="verified",
            implementation_signoff=_signoff(True),
            verification_signoff=_signoff(False),
        ),
        POLICY,
        target_floor="verified",
    )
    assert _evaluation(unsigned, "verified").eligible is False

    planned = reconcile_volume(
        _volume(evidence=["planned:evidence"]),
        _accountability(
            status="verified",
            implementation_signoff=_signoff(True),
            verification_signoff=_signoff(True),
        ),
        POLICY,
        target_floor="verified",
    )
    assert _evaluation(planned, "verified").eligible is False

    verified = reconcile_volume(
        _volume(),
        _accountability(
            status="verified",
            implementation_signoff=_signoff(True),
            verification_signoff=_signoff(True),
        ),
        POLICY,
        target_floor="verified",
    )
    assert _evaluation(verified, "verified").eligible is True
    assert verified.target_floor_eligible is True


def test_hardened_and_production_reject_unresolved_gaps() -> None:
    decision = reconcile_volume(
        _volume(),
        _accountability(
            status="production",
            implementation_signoff=_signoff(True),
            verification_signoff=_signoff(True),
            evidence=["ledger:evidence"],
        ),
        POLICY,
        target_floor="hardened",
    )

    for state in ("hardened", "production"):
        evaluation = _evaluation(decision, state)
        assert evaluation.eligible is False
        assert any(
            "unresolved volume gaps remain" in blocker
            for blocker in evaluation.blockers
        )


def test_reconciler_never_skips_an_ineligible_intermediate_state() -> None:
    policy = deepcopy(POLICY)
    policy["implemented"]["required_nonempty_fields"] = [
        *policy["implemented"]["required_nonempty_fields"],
        "intermediate_only_requirement",
    ]
    decision = reconcile_volume(
        _volume(gaps=[]),
        _accountability(
            status="production",
            implementation_signoff=_signoff(True),
            verification_signoff=_signoff(True),
            evidence=["ledger:evidence"],
        ),
        policy,
        target_floor="production",
    )

    assert _evaluation(decision, "production").eligible is True
    assert _evaluation(decision, "implemented").eligible is False
    assert decision.highest_eligible_status == "specified"
    assert decision.promotion_candidate is None
    assert decision.target_floor_eligible is False


def test_invalid_current_claim_blocks_further_promotion() -> None:
    decision = reconcile_volume(
        _volume(
            status="implemented",
            tests=["planned:tests/test_example.py"],
        ),
        _accountability(
            status="production",
            implementation_signoff=_signoff(True),
            verification_signoff=_signoff(True),
            evidence=["ledger:evidence"],
        ),
        POLICY,
        target_floor="verified",
    )

    assert decision.current_claim_valid is False
    assert decision.current_claim_blockers
    assert decision.promotion_candidate is None
    assert decision.highest_eligible_status == "implemented"


def test_reconciliation_never_mutates_inputs() -> None:
    volume = _volume()
    accountability = _accountability()
    policy = deepcopy(POLICY)
    before = (deepcopy(volume), deepcopy(accountability), deepcopy(policy))

    reconcile_volume(
        volume,
        accountability,
        policy,
        target_floor="verified",
    )

    assert (volume, accountability, policy) == before


def test_identity_mismatch_fails_closed() -> None:
    with pytest.raises(
        MaturityReconciliationError,
        match="accountability record identity mismatch",
    ):
        reconcile_volume(
            _volume(),
            _accountability(id="ACC-WRONG"),
            POLICY,
            target_floor="verified",
        )

@pytest.mark.parametrize(
    "status",
    ("passing", "done", "closed", "accepted_risk"),
)
def test_generic_lifecycle_terminal_does_not_imply_maturity(
    status: str,
) -> None:
    decision = reconcile_volume(
        _volume(),
        _accountability(
            status=status,
            implementation_signoff=_signoff(True),
            verification_signoff=_signoff(True),
            evidence=["ledger:evidence"],
        ),
        POLICY,
        target_floor="production",
    )

    assert _evaluation(decision, "implemented").eligible is False
    assert _evaluation(decision, "verified").eligible is False
    assert _evaluation(decision, "production").eligible is False
    assert decision.target_floor_eligible is False
    assert decision.promotion_candidate == "scaffolded"

def test_implementation_status_cannot_lead_accountability() -> None:
    with pytest.raises(
        MaturityReconciliationError,
        match="exceeds explicit accountability maturity",
    ):
        reconcile_volume(
            _volume(implementation_status="verified"),
            _accountability(
                status="implemented",
                implementation_signoff=_signoff(True),
            ),
            POLICY,
            target_floor="verified",
        )


@pytest.mark.parametrize(
    "status",
    ("passing", "done", "closed", "accepted_risk"),
)
def test_generic_lifecycle_terminal_has_no_implementation_candidate(
    status: str,
) -> None:
    decision = reconcile_volume(
        _volume(gaps=[]),
        _accountability(
            status=status,
            implementation_signoff=_signoff(True),
            verification_signoff=_signoff(True),
            evidence=["ledger:evidence"],
        ),
        POLICY,
        target_floor="production",
    )

    assert decision.accountability_maturity_status is None
    assert decision.implementation_status_candidate is None

def test_source_digest_changes_when_maturity_policy_changes() -> None:
    volume = _volume()
    accountability = _accountability()
    baseline = reconcile_volume(
        volume,
        accountability,
        POLICY,
        target_floor="verified",
    )
    changed_policy = deepcopy(POLICY)
    changed_policy["verified"]["required_nonempty_fields"] = [
        *changed_policy["verified"]["required_nonempty_fields"],
        "extra_evidence",
    ]
    changed = reconcile_volume(
        volume,
        accountability,
        changed_policy,
        target_floor="verified",
    )

    assert changed.source_digest != baseline.source_digest

def test_reference_validator_blocks_unresolved_repository_paths() -> None:
    decision = reconcile_volume(
        _volume(
            implementation_paths=["missing/module.py"],
            tests=["tests/test_example.py"],
        ),
        _accountability(
            status="implemented",
            implementation_signoff=_signoff(True),
        ),
        POLICY,
        target_floor="implemented",
        reference_validator=lambda field, reference: (
            reference != "missing/module.py"
        ),
    )

    implemented = _evaluation(decision, "implemented")
    assert implemented.eligible is False
    assert any(
        "implementation_paths contains unresolved repository references" in blocker
        and "missing/module.py" in blocker
        for blocker in implemented.blockers
    )


def test_reference_validator_does_not_affect_planning_only_scaffolded() -> None:
    decision = reconcile_volume(
        _volume(implementation_paths=["missing/module.py"]),
        _accountability(),
        POLICY,
        target_floor="verified",
        reference_validator=lambda field, reference: False,
    )

    assert _evaluation(decision, "scaffolded").eligible is True
    assert decision.promotion_candidate == "scaffolded"
