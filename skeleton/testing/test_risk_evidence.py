from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from skeleton.contracts.canonical import EvidenceRef
from skeleton.contracts.risk_evidence import (
    AcceptedRisk,
    RiskDisposition,
    RiskEvidenceBinding,
    RiskEvidenceError,
    RiskKind,
    RiskObligation,
    RiskSeverity,
    canonical_digest,
    evaluate_risk_binding,
    make_obligation_id,
)


NOW = datetime(2026, 9, 27, 20, 0, tzinfo=timezone.utc)
HEAD = "a" * 40


def _obligation(
    *,
    kind: RiskKind = RiskKind.RISK,
    severity: RiskSeverity = RiskSeverity.HIGH,
    blocking: bool = True,
    modes: tuple[str, ...] = (),
    statement: str = "risk statement",
) -> RiskObligation:
    source_ref = "VOL-999:risk:fixture"
    if kind is RiskKind.GAP:
        source_ref = "VOL-999:gap:fixture"
    elif kind is RiskKind.ADVERSARIAL:
        source_ref = "AC-99"
    return RiskObligation(
        obligation_id=make_obligation_id(kind, source_ref, statement),
        kind=kind,
        source_ref=source_ref,
        statement=statement,
        source_digest=canonical_digest(
            {"kind": kind.value, "source_ref": source_ref, "statement": statement}
        ),
        default_severity=severity,
        blocking_by_default=blocking,
        required_evidence_modes=modes,
    )


def _evidence(category: str = "test") -> EvidenceRef:
    return EvidenceRef(
        source=f"pytest:{category}",
        digest=canonical_digest({"category": category}),
        category=category,
    )


def _evidence_binding(
    obligation: RiskObligation,
    *,
    severity: RiskSeverity = RiskSeverity.HIGH,
    evidence: tuple[EvidenceRef, ...] | None = None,
    review_at: datetime | None = None,
) -> RiskEvidenceBinding:
    return RiskEvidenceBinding(
        obligation_id=obligation.obligation_id,
        obligation_digest=obligation.obligation_digest,
        owner_id="owner:security",
        severity=severity,
        disposition=RiskDisposition.EVIDENCE,
        bound_at=NOW - timedelta(hours=1),
        review_at=review_at or NOW + timedelta(days=30),
        evidence=evidence or (_evidence(),),
    )


def _accepted(
    obligation: RiskObligation,
    *,
    severity: RiskSeverity = RiskSeverity.HIGH,
    review_at: datetime | None = None,
    expires_at: datetime | None = None,
) -> AcceptedRisk:
    return AcceptedRisk(
        obligation_id=obligation.obligation_id,
        obligation_digest=obligation.obligation_digest,
        owner_id="owner:security",
        severity=severity,
        accepted_at=NOW - timedelta(days=1),
        review_at=review_at or NOW + timedelta(days=7),
        expires_at=expires_at or NOW + timedelta(days=30),
        signer_id="human:risk-owner",
        signer_type="human",
        git_sha=HEAD,
        signature_method="github_identity",
        signature_ref="https://github.com/Apeloff1/Skeleton/commit/" + HEAD,
        statement="Explicitly accept this bounded risk until review.",
    )


def test_obligation_identity_is_deterministic_and_statement_bound() -> None:
    left = _obligation()
    right = _obligation()

    assert left.obligation_id == right.obligation_id
    assert left.obligation_digest == right.obligation_digest

    changed = _obligation(statement="different risk statement")
    assert changed.obligation_id != left.obligation_id
    assert changed.obligation_digest != left.obligation_digest


def test_missing_unclassified_risk_fails_closed() -> None:
    obligation = _obligation(
        severity=RiskSeverity.UNCLASSIFIED,
        blocking=False,
    )

    decision = evaluate_risk_binding(
        obligation,
        None,
        evaluated_at=NOW,
    )

    assert decision.resolved is False
    assert decision.blocking is True
    assert decision.severity == "unclassified"
    assert decision.blockers == ("classification and binding required",)


def test_materialized_evidence_resolves_high_risk() -> None:
    obligation = _obligation()
    decision = evaluate_risk_binding(
        obligation,
        _evidence_binding(obligation),
        evaluated_at=NOW,
    )

    assert decision.resolved is True
    assert decision.blocking is True
    assert decision.disposition == "evidence"
    assert decision.blockers == ()


def test_planned_evidence_source_is_rejected() -> None:
    obligation = _obligation()

    with pytest.raises(RiskEvidenceError, match="materialized"):
        _evidence_binding(
            obligation,
            evidence=(
                EvidenceRef(
                    source="planned:tests/test_future.py",
                    digest="1" * 64,
                    category="test",
                ),
            ),
        )


def test_adversarial_evidence_must_cover_every_required_mode() -> None:
    obligation = _obligation(
        kind=RiskKind.ADVERSARIAL,
        modes=("fault_injection", "recovery_drill"),
    )
    incomplete = _evidence_binding(
        obligation,
        evidence=(_evidence("fault_injection"),),
    )
    rejected = evaluate_risk_binding(
        obligation,
        incomplete,
        evaluated_at=NOW,
    )
    assert rejected.resolved is False
    assert rejected.blockers == (
        "required evidence modes missing: recovery_drill",
    )

    complete = _evidence_binding(
        obligation,
        evidence=(
            _evidence("fault_injection"),
            _evidence("recovery_drill"),
        ),
    )
    accepted = evaluate_risk_binding(
        obligation,
        complete,
        evaluated_at=NOW,
    )
    assert accepted.resolved is True


def test_binding_digest_mismatch_fails_closed() -> None:
    obligation = _obligation()
    binding = RiskEvidenceBinding(
        obligation_id=obligation.obligation_id,
        obligation_digest="f" * 64,
        owner_id="owner:security",
        severity=RiskSeverity.HIGH,
        disposition=RiskDisposition.EVIDENCE,
        bound_at=NOW - timedelta(hours=1),
        review_at=NOW + timedelta(days=1),
        evidence=(_evidence(),),
    )

    decision = evaluate_risk_binding(
        obligation,
        binding,
        evaluated_at=NOW,
    )

    assert decision.resolved is False
    assert "binding obligation_digest mismatch" in decision.blockers


def test_overdue_binding_review_fails_closed() -> None:
    obligation = _obligation()
    binding = _evidence_binding(
        obligation,
        review_at=NOW - timedelta(seconds=1),
    )

    decision = evaluate_risk_binding(
        obligation,
        binding,
        evaluated_at=NOW,
    )

    assert decision.resolved is False
    assert decision.blockers == ("binding review is overdue",)


def test_signed_time_bounded_high_risk_acceptance_resolves() -> None:
    obligation = _obligation()
    acceptance = _accepted(obligation)
    binding = RiskEvidenceBinding(
        obligation_id=obligation.obligation_id,
        obligation_digest=obligation.obligation_digest,
        owner_id="owner:security",
        severity=RiskSeverity.HIGH,
        disposition=RiskDisposition.ACCEPTED_RISK,
        bound_at=NOW - timedelta(hours=1),
        review_at=NOW + timedelta(days=7),
        accepted_risk=acceptance,
    )

    decision = evaluate_risk_binding(
        obligation,
        binding,
        evaluated_at=NOW,
    )

    assert decision.resolved is True
    assert decision.disposition == "accepted_risk"


def test_expired_or_review_overdue_acceptance_fails_closed() -> None:
    obligation = _obligation()
    acceptance = _accepted(
        obligation,
        review_at=NOW - timedelta(hours=1),
        expires_at=NOW + timedelta(days=1),
    )
    binding = RiskEvidenceBinding(
        obligation_id=obligation.obligation_id,
        obligation_digest=obligation.obligation_digest,
        owner_id="owner:security",
        severity=RiskSeverity.HIGH,
        disposition=RiskDisposition.ACCEPTED_RISK,
        bound_at=NOW - timedelta(days=2),
        review_at=NOW + timedelta(days=1),
        accepted_risk=acceptance,
    )

    decision = evaluate_risk_binding(
        obligation,
        binding,
        evaluated_at=NOW,
    )

    assert decision.resolved is False
    assert "accepted-risk review/expiry is stale" in decision.blockers


def test_accepted_risk_identity_must_bind_exact_obligation() -> None:
    obligation = _obligation()
    other = _obligation(statement="different")
    acceptance = _accepted(other)
    binding = RiskEvidenceBinding(
        obligation_id=obligation.obligation_id,
        obligation_digest=obligation.obligation_digest,
        owner_id="owner:security",
        severity=RiskSeverity.HIGH,
        disposition=RiskDisposition.ACCEPTED_RISK,
        bound_at=NOW - timedelta(hours=1),
        review_at=NOW + timedelta(days=7),
        accepted_risk=acceptance,
    )

    decision = evaluate_risk_binding(
        obligation,
        binding,
        evaluated_at=NOW,
    )

    assert decision.resolved is False
    assert "accepted-risk obligation_id mismatch" in decision.blockers
    assert "accepted-risk obligation_digest mismatch" in decision.blockers


def test_gap_cannot_be_downgraded_to_non_blocking() -> None:
    obligation = _obligation(
        kind=RiskKind.GAP,
        severity=RiskSeverity.HIGH,
        blocking=True,
    )
    binding = RiskEvidenceBinding(
        obligation_id=obligation.obligation_id,
        obligation_digest=obligation.obligation_digest,
        owner_id="owner:security",
        severity=RiskSeverity.LOW,
        disposition=RiskDisposition.NON_BLOCKING,
        bound_at=NOW - timedelta(hours=1),
        review_at=NOW + timedelta(days=30),
    )

    decision = evaluate_risk_binding(
        obligation,
        binding,
        evaluated_at=NOW,
    )

    assert decision.resolved is False
    assert decision.blocking is True
    assert "gap/adversarial obligations cannot be declared non-blocking" in (
        decision.blockers
    )


def test_low_risk_can_be_explicitly_non_blocking() -> None:
    obligation = _obligation(
        severity=RiskSeverity.UNCLASSIFIED,
        blocking=False,
    )
    binding = RiskEvidenceBinding(
        obligation_id=obligation.obligation_id,
        obligation_digest=obligation.obligation_digest,
        owner_id="owner:product",
        severity=RiskSeverity.LOW,
        disposition=RiskDisposition.NON_BLOCKING,
        bound_at=NOW - timedelta(hours=1),
        review_at=NOW + timedelta(days=30),
    )

    decision = evaluate_risk_binding(
        obligation,
        binding,
        evaluated_at=NOW,
    )

    assert decision.resolved is True
    assert decision.blocking is False
    assert decision.severity == "low"


def test_non_blocking_rejects_high_severity() -> None:
    obligation = _obligation()

    with pytest.raises(RiskEvidenceError, match="low/medium"):
        RiskEvidenceBinding(
            obligation_id=obligation.obligation_id,
            obligation_digest=obligation.obligation_digest,
            owner_id="owner:security",
            severity=RiskSeverity.HIGH,
            disposition=RiskDisposition.NON_BLOCKING,
            bound_at=NOW - timedelta(hours=1),
            review_at=NOW + timedelta(days=30),
        )


def test_accepted_risk_rejects_low_severity() -> None:
    obligation = _obligation()

    with pytest.raises(RiskEvidenceError, match="high/critical"):
        _accepted(obligation, severity=RiskSeverity.LOW)


def test_evidence_order_and_duplicates_do_not_change_binding_payload() -> None:
    obligation = _obligation()
    first = _evidence("a")
    second = _evidence("b")
    left = _evidence_binding(
        obligation,
        evidence=(first, second, first),
    )
    right = _evidence_binding(
        obligation,
        evidence=(second, first),
    )

    assert left.as_dict() == right.as_dict()

def test_accepted_risk_rejects_non_human_signer() -> None:
    obligation = _obligation()

    with pytest.raises(RiskEvidenceError, match="human signer"):
        AcceptedRisk(
            obligation_id=obligation.obligation_id,
            obligation_digest=obligation.obligation_digest,
            owner_id="owner:security",
            severity=RiskSeverity.HIGH,
            accepted_at=NOW - timedelta(days=1),
            review_at=NOW + timedelta(days=7),
            expires_at=NOW + timedelta(days=30),
            signer_id="ci:auto",
            signer_type="ci",
            git_sha=HEAD,
            signature_method="github_identity",
            signature_ref="https://github.com/Apeloff1/Skeleton/actions/runs/1",
            statement="Automated acceptance is forbidden.",
        )


def test_accepted_risk_rejects_unapproved_signature_method() -> None:
    obligation = _obligation()

    with pytest.raises(RiskEvidenceError, match="not approved"):
        AcceptedRisk(
            obligation_id=obligation.obligation_id,
            obligation_digest=obligation.obligation_digest,
            owner_id="owner:security",
            severity=RiskSeverity.HIGH,
            accepted_at=NOW - timedelta(days=1),
            review_at=NOW + timedelta(days=7),
            expires_at=NOW + timedelta(days=30),
            signer_id="human:risk-owner",
            signer_type="human",
            git_sha=HEAD,
            signature_method="unsigned_note",
            signature_ref="note:1",
            statement="Weak signature methods are forbidden.",
        )

