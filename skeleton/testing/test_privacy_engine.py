from __future__ import annotations

import pytest

from skeleton.ai.runtime.security.privacy_engine import (
    PrivacyDecision,
    PrivacyEngineError,
    PrivacyLabel,
    PurposeGrant,
    derive_privacy_label,
    evaluate_privacy_use,
)


def _label(
    label_id: str = "label-a",
    *,
    classification: str = "confidential",
    purposes: tuple[str, ...] = ("assist", "research"),
    jurisdictions: tuple[str, ...] = ("eu", "no"),
) -> PrivacyLabel:
    return PrivacyLabel(
        label_id=label_id,
        classification=classification,
        allowed_purposes=purposes,
        jurisdiction_scopes=jurisdictions,
        source_ref=f"source:{label_id}",
    )


def _grant(
    *,
    subject: str = "user-a",
    purpose: str = "assist",
    jurisdictions: tuple[str, ...] = ("eu", "no"),
    expires: int = 2_000,
) -> PurposeGrant:
    return PurposeGrant(
        grant_id="grant-a",
        subject_id=subject,
        purpose=purpose,
        jurisdiction_scopes=jurisdictions,
        expires_at_ns=expires,
    )


def test_privacy_label_is_canonical_and_content_addressable() -> None:
    label = _label(
        purposes=("research", "assist", "assist"),
        jurisdictions=("no", "eu", "eu"),
    )

    assert label.allowed_purposes == ("assist", "research")
    assert label.jurisdiction_scopes == ("eu", "no")
    assert len(label.digest) == 64


def test_derived_label_cannot_weaken_parent_classification_or_scope() -> None:
    broad = _label(
        "broad",
        classification="internal",
        purposes=("assist", "research"),
        jurisdictions=("eu", "no"),
    )
    strict = _label(
        "strict",
        classification="restricted",
        purposes=("assist",),
        jurisdictions=("no",),
    )

    derived = derive_privacy_label(
        label_id="derived",
        parents=(broad, strict),
        source_ref="artifact:derived",
    )

    assert derived.classification == "restricted"
    assert derived.allowed_purposes == ("assist",)
    assert derived.jurisdiction_scopes == ("no",)
    assert derived.parent_label_digests == tuple(
        sorted((broad.digest, strict.digest))
    )


def test_derived_label_is_deterministic_across_parent_order() -> None:
    left = _label(
        "left",
        classification="confidential",
        purposes=("assist", "research"),
        jurisdictions=("eu", "no"),
    )
    right = _label(
        "right",
        classification="internal",
        purposes=("assist",),
        jurisdictions=("no",),
    )

    first = derive_privacy_label(
        label_id="derived",
        parents=(left, right),
        source_ref="artifact:derived",
    )
    second = derive_privacy_label(
        label_id="derived",
        parents=(right, left),
        source_ref="artifact:derived",
    )

    assert first == second
    assert first.digest == second.digest


def test_derived_label_fails_closed_without_common_purpose() -> None:
    assist = _label("assist", purposes=("assist",))
    research = _label("research", purposes=("research",))

    with pytest.raises(PrivacyEngineError, match="no common allowed purpose"):
        derive_privacy_label(
            label_id="derived",
            parents=(assist, research),
            source_ref="artifact:derived",
        )


def test_derived_label_fails_closed_without_common_jurisdiction() -> None:
    eu = _label("eu", jurisdictions=("eu",))
    us = _label("us", jurisdictions=("us",))

    with pytest.raises(PrivacyEngineError, match="no common jurisdiction"):
        derive_privacy_label(
            label_id="derived",
            parents=(eu, us),
            source_ref="artifact:derived",
        )


def test_privacy_use_allows_matching_live_declared_scope() -> None:
    label = _label()
    grant = _grant()

    decision = evaluate_privacy_use(
        decision_id="decision-allowed",
        label=label,
        grant=grant,
        subject_id="user-a",
        purpose="assist",
        jurisdiction_scope="no",
        now_ns=1_000,
    )

    assert decision.allowed is True
    assert decision.reason_code == "allowed"
    assert decision.label_digest == label.digest
    assert decision.grant_digest == grant.digest
    assert decision.external_side_effects is False
    assert len(decision.digest) == 64


@pytest.mark.parametrize(
    ("subject", "purpose", "jurisdiction", "now_ns", "reason"),
    (
        ("user-b", "assist", "no", 1_000, "subject-mismatch"),
        ("user-a", "assist", "no", 2_000, "grant-expired"),
        ("user-a", "research", "no", 1_000, "grant-purpose-mismatch"),
        ("user-a", "assist", "us", 1_000, "grant-jurisdiction-denied"),
    ),
)
def test_privacy_use_fails_closed_for_grant_mismatch(
    subject: str,
    purpose: str,
    jurisdiction: str,
    now_ns: int,
    reason: str,
) -> None:
    decision = evaluate_privacy_use(
        decision_id=f"decision-{reason}",
        label=_label(jurisdictions=("eu", "no", "us")),
        grant=_grant(),
        subject_id=subject,
        purpose=purpose,
        jurisdiction_scope=jurisdiction,
        now_ns=now_ns,
    )

    assert decision.allowed is False
    assert decision.reason_code == reason
    assert decision.external_side_effects is False


def test_privacy_use_fails_when_label_disallows_purpose() -> None:
    decision = evaluate_privacy_use(
        decision_id="decision-purpose-denied",
        label=_label(purposes=("research",)),
        grant=_grant(purpose="assist"),
        subject_id="user-a",
        purpose="assist",
        jurisdiction_scope="no",
        now_ns=1_000,
    )

    assert decision.allowed is False
    assert decision.reason_code == "label-purpose-denied"


def test_privacy_use_fails_when_label_disallows_jurisdiction() -> None:
    decision = evaluate_privacy_use(
        decision_id="decision-jurisdiction-denied",
        label=_label(jurisdictions=("eu",)),
        grant=_grant(jurisdictions=("eu", "no")),
        subject_id="user-a",
        purpose="assist",
        jurisdiction_scope="no",
        now_ns=1_000,
    )

    assert decision.allowed is False
    assert decision.reason_code == "label-jurisdiction-denied"


def test_privacy_decision_cannot_claim_external_side_effects() -> None:
    with pytest.raises(PrivacyEngineError, match="external side effects"):
        PrivacyDecision(
            decision_id="decision-bad",
            label_digest="a" * 64,
            grant_digest="b" * 64,
            subject_id="user-a",
            purpose="assist",
            jurisdiction_scope="no",
            allowed=True,
            reason_code="allowed",
            evaluated_at_ns=1,
            external_side_effects=True,
        )


def test_privacy_contracts_reject_unknown_classification_and_empty_scope() -> None:
    with pytest.raises(PrivacyEngineError, match="classification must be"):
        _label(classification="secret")

    with pytest.raises(PrivacyEngineError, match="allowed_purpose must be non-empty"):
        _label(purposes=())

    with pytest.raises(PrivacyEngineError, match="jurisdiction_scope must be non-empty"):
        _grant(jurisdictions=())


def test_derived_label_requires_real_parent_contracts() -> None:
    with pytest.raises(PrivacyEngineError, match="at least one parent"):
        derive_privacy_label(
            label_id="derived",
            parents=(),
            source_ref="artifact:derived",
        )

    with pytest.raises(PrivacyEngineError, match="PrivacyLabel"):
        derive_privacy_label(
            label_id="derived",
            parents=(_label(), object()),  # type: ignore[arg-type]
            source_ref="artifact:derived",
        )
