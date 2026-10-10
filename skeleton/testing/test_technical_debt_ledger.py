from __future__ import annotations

import pytest

from skeleton.automation import technical_debt as compatibility
from skeleton.contracts import technical_debt as canonical
from skeleton.contracts.technical_debt import (
    DebtError,
    DebtEvidence,
    DebtEvidenceKind,
    DebtImpact,
    DebtItem,
    DebtLedger,
    DebtRetirement,
    debt_evidence_set_digest,
)


ARTIFACT = "1" * 64


def item(
    *,
    debt_id: str = "DEBT.1",
    owner_id: str = "OWNER.RUNTIME",
    contracts: tuple[str, ...] = ("CONTRACT.STATE",),
    impact: DebtImpact | None = None,
) -> DebtItem:
    return DebtItem(
        debt_id,
        "legacy serializer",
        contracts,
        owner_id,
        "replace with canonical codec",
        impact or DebtImpact(3, 4, 5),
    )


def evidence(
    subject: DebtItem,
    evidence_id: str,
    kind: DebtEvidenceKind,
    *,
    observed_tick: int = 1,
    passed: bool = True,
    producer_id: str = "WORKER.DEBT",
    verifier_id: str = "VERIFIER.DEBT",
    debt_digest: str | None = None,
) -> DebtEvidence:
    return DebtEvidence(
        evidence_id=evidence_id,
        debt_id=subject.debt_id,
        debt_digest=debt_digest or subject.digest,
        kind=kind,
        artifact_digest=ARTIFACT,
        observed_tick=observed_tick,
        passed=passed,
        producer_id=producer_id,
        verifier_id=verifier_id,
    )


def retirement_evidence(
    subject: DebtItem,
    *,
    observed_tick: int = 1,
) -> tuple[DebtEvidence, ...]:
    return (
        evidence(
            subject,
            "EVID.MIGRATION",
            DebtEvidenceKind.MIGRATION,
            observed_tick=observed_tick,
        ),
        evidence(
            subject,
            "EVID.COMPAT",
            DebtEvidenceKind.COMPATIBILITY,
            observed_tick=observed_tick,
        ),
        evidence(
            subject,
            "EVID.ROLLBACK",
            DebtEvidenceKind.ROLLBACK,
            observed_tick=observed_tick,
        ),
        evidence(
            subject,
            "EVID.VERIFY",
            DebtEvidenceKind.VERIFICATION,
            observed_tick=observed_tick,
            producer_id="WORKER.VERIFY",
            verifier_id="VERIFIER.INDEP",
        ),
    )


def receipt(
    subject: DebtItem,
    items: tuple[DebtEvidence, ...],
    *,
    verifier_id: str = "VERIFIER.INDEP",
    observed_tick: int = 2,
    debt_digest: str | None = None,
    evidence_set_digest: str | None = None,
) -> DebtRetirement:
    by_kind = {entry.kind: entry for entry in items}
    return DebtRetirement(
        debt_id=subject.debt_id,
        debt_digest=debt_digest or subject.digest,
        migration_evidence_id=by_kind[
            DebtEvidenceKind.MIGRATION
        ].evidence_id,
        compatibility_evidence_id=by_kind[
            DebtEvidenceKind.COMPATIBILITY
        ].evidence_id,
        rollback_evidence_id=by_kind[
            DebtEvidenceKind.ROLLBACK
        ].evidence_id,
        verification_evidence_id=by_kind[
            DebtEvidenceKind.VERIFICATION
        ].evidence_id,
        evidence_set_digest=(
            evidence_set_digest
            or debt_evidence_set_digest(items)
        ),
        verifier_id=verifier_id,
        observed_tick=observed_tick,
    )


def test_automation_surface_has_no_parallel_authority() -> None:
    assert compatibility.__all__ == canonical.__all__
    for name in canonical.__all__:
        assert getattr(compatibility, name) is getattr(canonical, name)


def test_debt_requires_owner_contract_and_disposition() -> None:
    subject = item()
    assert subject.owner_id == "OWNER.RUNTIME"
    assert subject.contract_ids == ("CONTRACT.STATE",)
    assert subject.target_disposition == "replace with canonical codec"


def test_interest_combines_operational_engineering_and_risk() -> None:
    subject = item()
    assert subject.impact.total == 12
    assert DebtLedger((subject,)).interest("DEBT.1") == 12


def test_active_debt_is_sorted_by_interest_then_identity() -> None:
    high = item(
        debt_id="DEBT.HIGH",
        impact=DebtImpact(10, 10, 10),
    )
    low_b = item(
        debt_id="DEBT.LOWB",
        impact=DebtImpact(1, 1, 1),
    )
    low_a = item(
        debt_id="DEBT.LOWA",
        impact=DebtImpact(1, 1, 1),
    )
    ledger = DebtLedger((low_b, high, low_a))
    assert tuple(entry.debt_id for entry in ledger.active_by_risk()) == (
        "DEBT.HIGH",
        "DEBT.LOWA",
        "DEBT.LOWB",
    )
    assert ledger.total_active_interest() == 36


def test_valid_retirement_requires_exact_evidence_set() -> None:
    subject = item()
    items = retirement_evidence(subject)
    ledger = DebtLedger((subject,), items)
    accepted = ledger.retire(receipt(subject, items))
    assert accepted.rollback_evidence_id == "EVID.ROLLBACK"
    assert ledger.active_by_risk() == ()


def test_unknown_debt_cannot_be_retired() -> None:
    known = item()
    foreign = item(debt_id="DEBT.9")
    items = retirement_evidence(foreign)
    foreign_receipt = receipt(foreign, items)
    ledger = DebtLedger((known,))
    with pytest.raises(DebtError, match="unknown debt"):
        ledger.retire(foreign_receipt)


def test_debt_cannot_be_retired_twice() -> None:
    subject = item()
    items = retirement_evidence(subject)
    ledger = DebtLedger((subject,), items)
    retirement = receipt(subject, items)
    ledger.retire(retirement)
    with pytest.raises(DebtError, match="already retired"):
        ledger.retire(retirement)


def test_retirement_receipt_is_runtime_typed() -> None:
    with pytest.raises(DebtError, match="receipt must"):
        DebtLedger((item(),)).retire("DEBT.1")  # type: ignore[arg-type]


def test_retirement_must_bind_exact_debt_revision() -> None:
    subject = item()
    items = retirement_evidence(subject)
    ledger = DebtLedger((subject,), items)
    stale = receipt(
        subject,
        items,
        debt_digest="0" * 64,
    )
    with pytest.raises(DebtError, match="retirement debt digest mismatch"):
        ledger.retire(stale)


def test_evidence_must_bind_exact_debt_revision_at_registry_time() -> None:
    subject = item()
    stale = evidence(
        subject,
        "EVID.STALE",
        DebtEvidenceKind.MIGRATION,
        debt_digest="0" * 64,
    )
    with pytest.raises(DebtError, match="evidence debt digest mismatch"):
        DebtLedger((subject,), (stale,))


def test_retirement_rejects_unknown_evidence_reference() -> None:
    subject = item()
    items = retirement_evidence(subject)
    ledger = DebtLedger((subject,), items[:-1])
    retirement = receipt(subject, items)
    with pytest.raises(DebtError, match="unknown evidence"):
        ledger.retire(retirement)


def test_retirement_rejects_failed_evidence() -> None:
    subject = item()
    items = list(retirement_evidence(subject))
    items[0] = evidence(
        subject,
        "EVID.MIGRATION",
        DebtEvidenceKind.MIGRATION,
        passed=False,
    )
    selected = tuple(items)
    ledger = DebtLedger((subject,), selected)
    with pytest.raises(DebtError, match="failed evidence"):
        ledger.retire(receipt(subject, selected))


def test_retirement_rejects_future_evidence() -> None:
    subject = item()
    items = retirement_evidence(subject, observed_tick=5)
    ledger = DebtLedger((subject,), items)
    with pytest.raises(DebtError, match="future evidence"):
        ledger.retire(
            receipt(
                subject,
                items,
                observed_tick=4,
            )
        )


def test_retirement_rejects_foreign_debt_evidence() -> None:
    first = item(debt_id="DEBT.1")
    second = item(debt_id="DEBT.2")
    first_items = list(retirement_evidence(first))
    foreign = evidence(
        second,
        "EVID.FOREIGN",
        DebtEvidenceKind.MIGRATION,
    )
    first_items[0] = foreign
    selected = tuple(first_items)
    ledger = DebtLedger(
        (first, second),
        selected,
    )
    retirement = DebtRetirement(
        debt_id=first.debt_id,
        debt_digest=first.digest,
        migration_evidence_id=foreign.evidence_id,
        compatibility_evidence_id="EVID.COMPAT",
        rollback_evidence_id="EVID.ROLLBACK",
        verification_evidence_id="EVID.VERIFY",
        evidence_set_digest=debt_evidence_set_digest(selected),
        verifier_id="VERIFIER.INDEP",
        observed_tick=2,
    )
    with pytest.raises(DebtError, match="foreign debt evidence"):
        ledger.retire(retirement)


def test_retirement_evidence_ids_are_kind_specific() -> None:
    subject = item()
    items = retirement_evidence(subject)
    ledger = DebtLedger((subject,), items)
    by_kind = {entry.kind: entry for entry in items}
    swapped = DebtRetirement(
        debt_id=subject.debt_id,
        debt_digest=subject.digest,
        migration_evidence_id=by_kind[
            DebtEvidenceKind.COMPATIBILITY
        ].evidence_id,
        compatibility_evidence_id=by_kind[
            DebtEvidenceKind.MIGRATION
        ].evidence_id,
        rollback_evidence_id=by_kind[
            DebtEvidenceKind.ROLLBACK
        ].evidence_id,
        verification_evidence_id=by_kind[
            DebtEvidenceKind.VERIFICATION
        ].evidence_id,
        evidence_set_digest=debt_evidence_set_digest(items),
        verifier_id="VERIFIER.INDEP",
        observed_tick=2,
    )
    with pytest.raises(DebtError, match="wrong kind"):
        ledger.retire(swapped)


def test_retirement_evidence_set_digest_must_match_exact_set() -> None:
    subject = item()
    items = retirement_evidence(subject)
    ledger = DebtLedger((subject,), items)
    mismatched = receipt(
        subject,
        items,
        evidence_set_digest="0" * 64,
    )
    with pytest.raises(DebtError, match="evidence set mismatch"):
        ledger.retire(mismatched)


def test_retirement_verifier_must_be_independent_of_owner() -> None:
    subject = item(owner_id="OWNER.RUNTIME")
    items = retirement_evidence(subject)
    ledger = DebtLedger((subject,), items)
    with pytest.raises(DebtError, match="independent"):
        ledger.retire(
            receipt(
                subject,
                items,
                verifier_id="OWNER.RUNTIME",
            )
        )


def test_verification_evidence_verifier_must_match_receipt() -> None:
    subject = item()
    items = retirement_evidence(subject)
    ledger = DebtLedger((subject,), items)
    with pytest.raises(DebtError, match="verifier mismatch"):
        ledger.retire(
            receipt(
                subject,
                items,
                verifier_id="VERIFIER.OTHER",
            )
        )


def test_verification_evidence_cannot_self_verify() -> None:
    subject = item()
    items = list(retirement_evidence(subject))
    items[-1] = evidence(
        subject,
        "EVID.VERIFY",
        DebtEvidenceKind.VERIFICATION,
        producer_id="VERIFIER.INDEP",
        verifier_id="VERIFIER.INDEP",
    )
    selected = tuple(items)
    ledger = DebtLedger((subject,), selected)
    with pytest.raises(DebtError, match="not independent"):
        ledger.retire(receipt(subject, selected))


def test_contract_exposure_query_tracks_active_and_retired_debt() -> None:
    subject = item(
        contracts=("CONTRACT.API", "CONTRACT.STATE"),
    )
    items = retirement_evidence(subject)
    ledger = DebtLedger((subject,), items)
    assert tuple(
        entry.debt_id
        for entry in ledger.debts_for_contract("CONTRACT.API")
    ) == ("DEBT.1",)

    ledger.retire(receipt(subject, items))
    assert ledger.debts_for_contract("CONTRACT.API") == ()
    assert tuple(
        entry.debt_id
        for entry in ledger.debts_for_contract(
            "CONTRACT.API",
            include_retired=True,
        )
    ) == ("DEBT.1",)


def test_owner_interest_tracks_active_and_historical_interest() -> None:
    first = item(
        debt_id="DEBT.1",
        owner_id="OWNER.RUNTIME",
        impact=DebtImpact(3, 4, 5),
    )
    second = item(
        debt_id="DEBT.2",
        owner_id="OWNER.RUNTIME",
        impact=DebtImpact(1, 1, 1),
    )
    items = retirement_evidence(first)
    ledger = DebtLedger((first, second), items)
    assert ledger.owner_interest("OWNER.RUNTIME") == 15
    ledger.retire(receipt(first, items))
    assert ledger.owner_interest("OWNER.RUNTIME") == 3
    assert (
        ledger.owner_interest(
            "OWNER.RUNTIME",
            include_retired=True,
        )
        == 15
    )


def test_unknown_interest_query_fails_with_domain_error() -> None:
    with pytest.raises(DebtError, match="unknown debt"):
        DebtLedger((item(),)).interest("DEBT.9")


def test_debt_impact_rejects_boolean_non_integer_and_negative_interest() -> None:
    with pytest.raises(DebtError, match="nonnegative integer"):
        DebtImpact(True, 1, 1)
    with pytest.raises(DebtError, match="nonnegative integer"):
        DebtImpact(1, 1.5, 1)  # type: ignore[arg-type]
    with pytest.raises(DebtError, match="nonnegative integer"):
        DebtImpact(1, 1, -1)


def test_duplicate_debt_contract_and_evidence_identity_rejected() -> None:
    with pytest.raises(DebtError, match="duplicate affected contract"):
        item(
            debt_id="DEBT.2",
            contracts=("CONTRACT.X", "CONTRACT.X"),
        )

    subject = item()
    with pytest.raises(DebtError, match="duplicate debt identity"):
        DebtLedger((subject, subject))

    one = evidence(
        subject,
        "EVID.1",
        DebtEvidenceKind.MIGRATION,
    )
    with pytest.raises(DebtError, match="duplicate debt evidence id"):
        DebtLedger((subject,), (one, one))


def test_evidence_set_identity_is_order_independent() -> None:
    subject = item()
    items = retirement_evidence(subject)
    assert debt_evidence_set_digest(items) == debt_evidence_set_digest(
        reversed(items)
    )


def test_evidence_set_rejects_duplicate_ids() -> None:
    subject = item()
    entry = evidence(
        subject,
        "EVID.1",
        DebtEvidenceKind.MIGRATION,
    )
    with pytest.raises(DebtError, match="duplicate debt evidence"):
        debt_evidence_set_digest((entry, entry))


def test_ledger_identity_is_order_independent() -> None:
    first = item(debt_id="DEBT.1")
    second = item(debt_id="DEBT.2")
    first_evidence = evidence(
        first,
        "EVID.1",
        DebtEvidenceKind.MIGRATION,
    )
    second_evidence = evidence(
        second,
        "EVID.2",
        DebtEvidenceKind.MIGRATION,
    )
    a = DebtLedger(
        (first, second),
        (first_evidence, second_evidence),
    )
    b = DebtLedger(
        (second, first),
        (second_evidence, first_evidence),
    )
    assert a.ledger_digest == b.ledger_digest


def test_snapshot_changes_when_debt_is_retired_but_ledger_identity_does_not() -> None:
    subject = item()
    items = retirement_evidence(subject)
    ledger = DebtLedger((subject,), items)
    before = ledger.snapshot()
    ledger.retire(receipt(subject, items))
    after = ledger.snapshot()
    assert before.ledger_digest == after.ledger_digest
    assert before.digest != after.digest
    assert before.active_debt_ids == ("DEBT.1",)
    assert after.active_debt_ids == ()


def test_include_retired_flags_are_strict_booleans() -> None:
    ledger = DebtLedger((item(),))
    with pytest.raises(TypeError, match="include_retired"):
        ledger.debts_for_contract(
            "CONTRACT.STATE",
            include_retired=1,  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError, match="include_retired"):
        ledger.owner_interest(
            "OWNER.RUNTIME",
            include_retired=1,  # type: ignore[arg-type]
        )


def test_invalid_container_types_fail_closed() -> None:
    with pytest.raises(TypeError, match="DebtItem"):
        DebtLedger(("DEBT.1",))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="DebtEvidence"):
        DebtLedger(
            (item(),),
            ("EVID.1",),  # type: ignore[arg-type]
        )
