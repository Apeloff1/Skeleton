from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.contracts.canonical import EvidenceRef
from skeleton.contracts.p1_failure_journeys import (
    P1_FAILURE_JOURNEY_ASSERTIONS,
    P1_RECOVERY_REQUIRED_JOURNEYS,
    P1_REQUIRED_FAILURE_JOURNEYS,
    FailureJourneyFamily,
    FailureJourneyReceipt,
    P1FailureJourneyError,
    qualify_p1_failure_journeys,
)
from skeleton.contracts.p1_terminal_evidence import (
    P1_TERMINAL_REQUIRED_TASKS,
    P1TerminalEvidenceDecision,
    TerminalTaskEvidence,
)


HEAD = "a" * 40
REPOSITORY = "Apeloff1/Skeleton"


def _terminal(**overrides: object) -> P1TerminalEvidenceDecision:
    values: dict[str, object] = {
        "accepted": True,
        "promotion_ready": True,
        "reasons": (),
        "promotion_blockers": (),
        "repository": REPOSITORY,
        "commit_sha": HEAD,
        "task_evidence": tuple(
            TerminalTaskEvidence(
                task_id=task_id,
                accountability_id=accountability_id,
                subject_digest="1" * 64,
                receipt_digest=(
                    f"{index:x}"[-1] * 64
                    if index < 16
                    else "2" * 64
                ),
                evidence_digest="e" * 64,
            )
            for index, (task_id, accountability_id)
            in enumerate(P1_TERMINAL_REQUIRED_TASKS, start=1)
        ),
        "maturity_report_digest": "f" * 64,
        "maturity_coverage_digest": "2" * 64,
        "primary_volume_count": 3,
        "blocking_volume_keys": (),
    }
    values.update(overrides)
    return P1TerminalEvidenceDecision(**values)


def _receipt(
    family: FailureJourneyFamily,
    **overrides: object,
) -> FailureJourneyReceipt:
    recovered = family in P1_RECOVERY_REQUIRED_JOURNEYS
    digit = str((list(FailureJourneyFamily).index(family) % 8) + 1)
    values: dict[str, object] = {
        "family": family,
        "repository": REPOSITORY,
        "commit_sha": HEAD,
        "verifier_id": f"verifier:{family.value}",
        "verifier_digest": digit * 64,
        "test_manifest_digest": "9" * 64,
        "evidence": (
            EvidenceRef(
                source=f"journey://{family.value}",
                digest="d" * 64,
                category="failure_journey",
            ),
        ),
        "assertions": P1_FAILURE_JOURNEY_ASSERTIONS[family],
        "passed": True,
        "independent": True,
        "recovered": recovered,
        "production_mutation_count": 0,
    }
    values.update(overrides)
    return FailureJourneyReceipt(**values)


def _receipts() -> tuple[FailureJourneyReceipt, ...]:
    return tuple(_receipt(family) for family in P1_REQUIRED_FAILURE_JOURNEYS)


def _qualify(
    *,
    terminal: P1TerminalEvidenceDecision | None = None,
    receipts: tuple[FailureJourneyReceipt, ...] | None = None,
):
    return qualify_p1_failure_journeys(
        terminal_evidence=terminal or _terminal(),
        receipts=receipts or _receipts(),
        expected_repository=REPOSITORY,
        expected_head=HEAD,
    )


def test_complete_failure_journey_set_qualifies() -> None:
    decision = _qualify()

    assert decision.accepted is True
    assert decision.reasons == ()
    assert decision.repository == REPOSITORY
    assert decision.commit_sha == HEAD
    assert decision.terminal_evidence_digest == _terminal().decision_digest
    assert tuple(item.family for item in decision.journey_evidence) == (
        P1_REQUIRED_FAILURE_JOURNEYS
    )
    evidence = decision.accepted_evidence_ref()
    assert evidence.category == "p1_failure_journey_qualification"
    assert evidence.digest == decision.decision_digest


def test_receipt_order_does_not_change_decision_identity() -> None:
    left = _qualify(receipts=_receipts())
    right = _qualify(receipts=tuple(reversed(_receipts())))

    assert left.accepted is True
    assert right.accepted is True
    assert left.decision_digest == right.decision_digest


@pytest.mark.parametrize(
    ("changes", "reason"),
    (
        (
            {"accepted": False, "promotion_ready": False},
            "terminal-evidence-rejected",
        ),
        ({"promotion_ready": False}, "terminal-evidence-not-promotion-ready"),
        (
            {"promotion_blockers": ("VOL-001:blocking",), "promotion_ready": False},
            "terminal-promotion-blockers-present",
        ),
        ({"repository": "Other/Skeleton"}, "terminal-repository-mismatch"),
        ({"commit_sha": "b" * 40}, "terminal-exact-head-mismatch"),
    ),
)
def test_terminal_bundle_must_be_exact_and_ready(
    changes: dict[str, object],
    reason: str,
) -> None:
    terminal = _terminal(**changes)
    decision = _qualify(terminal=terminal)

    assert decision.accepted is False
    assert reason in decision.reasons


def test_terminal_task_provenance_cannot_be_omitted() -> None:
    terminal = _terminal(
        task_evidence=_terminal().task_evidence[1:],
    )
    decision = _qualify(terminal=terminal)

    assert decision.accepted is False
    assert "terminal-missing-task:P1-EVID-06" in decision.reasons


def test_terminal_task_accountability_substitution_blocks() -> None:
    evidence = list(_terminal().task_evidence)
    evidence[0] = replace(
        evidence[0],
        accountability_id="ACC-P1-EVID-05",
    )
    decision = _qualify(
        terminal=_terminal(task_evidence=tuple(evidence))
    )

    assert decision.accepted is False
    assert (
        "terminal-accountability-mismatch:P1-EVID-06"
        in decision.reasons
    )


@pytest.mark.parametrize("family", P1_REQUIRED_FAILURE_JOURNEYS)
def test_every_failure_family_is_mandatory(
    family: FailureJourneyFamily,
) -> None:
    receipts = tuple(
        item for item in _receipts() if item.family is not family
    )
    decision = _qualify(receipts=receipts)

    assert decision.accepted is False
    assert f"missing-journey:{family.value}" in decision.reasons


def test_duplicate_failure_family_is_rejected() -> None:
    receipts = _receipts()
    decision = _qualify(receipts=(*receipts, receipts[0]))

    assert decision.accepted is False
    assert "duplicate-journey:clean_machine" in decision.reasons


@pytest.mark.parametrize(
    ("field", "value", "suffix"),
    (
        ("commit_sha", "b" * 40, "exact-head-mismatch"),
        ("repository", "Other/Skeleton", "repository-mismatch"),
        ("passed", False, "journey-failed"),
        ("independent", False, "not-independent"),
        ("production_mutation_count", 1, "production-mutated"),
    ),
)
def test_journey_receipts_fail_closed(
    field: str,
    value: object,
    suffix: str,
) -> None:
    receipts = list(_receipts())
    receipts[0] = replace(receipts[0], **{field: value})

    decision = _qualify(receipts=tuple(receipts))

    assert decision.accepted is False
    assert f"clean_machine:{suffix}" in decision.reasons


@pytest.mark.parametrize(
    "family",
    tuple(sorted(P1_RECOVERY_REQUIRED_JOURNEYS, key=lambda item: item.value)),
)
def test_recovery_families_require_verified_recovery(
    family: FailureJourneyFamily,
) -> None:
    receipts = list(_receipts())
    index = list(P1_REQUIRED_FAILURE_JOURNEYS).index(family)
    receipts[index] = replace(receipts[index], recovered=False)

    decision = _qualify(receipts=tuple(receipts))

    assert decision.accepted is False
    assert f"{family.value}:recovery-not-verified" in decision.reasons


@pytest.mark.parametrize("family", P1_REQUIRED_FAILURE_JOURNEYS)
def test_family_specific_assertions_are_mandatory(
    family: FailureJourneyFamily,
) -> None:
    receipts = list(_receipts())
    index = list(P1_REQUIRED_FAILURE_JOURNEYS).index(family)
    required = P1_FAILURE_JOURNEY_ASSERTIONS[family]
    receipts[index] = replace(
        receipts[index],
        assertions=required[1:],
    )

    decision = _qualify(receipts=tuple(receipts))

    assert decision.accepted is False
    assert (
        f"{family.value}:missing-assertion:{required[0]}"
        in decision.reasons
    )


def test_verifier_identity_must_be_unique_across_journeys() -> None:
    receipts = list(_receipts())
    receipts[1] = replace(
        receipts[1],
        verifier_id=receipts[0].verifier_id,
    )

    decision = _qualify(receipts=tuple(receipts))

    assert decision.accepted is False
    assert (
        f"duplicate-verifier:{receipts[0].verifier_id}"
        in decision.reasons
    )


def test_rejected_failure_bundle_cannot_become_promotion_evidence() -> None:
    receipts = list(_receipts())
    receipts[0] = replace(receipts[0], passed=False)

    decision = _qualify(receipts=tuple(receipts))

    assert decision.accepted is False
    with pytest.raises(
        P1FailureJourneyError,
        match="cannot become evidence",
    ):
        decision.accepted_evidence_ref()
