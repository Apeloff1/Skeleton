import pytest

from skeleton.school.decision_ledger import DecisionDisposition, DecisionLedger, EvidenceKind, EvidenceRef


def make_ledger() -> DecisionLedger:
    ledger = DecisionLedger()
    ledger.register_evidence(EvidenceRef("e", EvidenceKind.OBSERVATION, "student", "signal"))
    ledger.append(session_id="s", decision_id="d1", domain="school", action="practice", evidence=("e",))
    return ledger


def test_supersession_is_first_class_and_hash_audited() -> None:
    ledger = make_ledger()
    replacement = ledger.supersede("d1", replacement_id="d2")

    assert replacement.supersedes == "d1"
    assert replacement.predecessors == ("d1",)
    assert "supersedes:d1" not in replacement.rationale
    assert ledger.superseded_ids() == frozenset({"d1"})
    ledger.verify()


def test_supersession_requires_an_existing_prior_decision() -> None:
    ledger = make_ledger()
    with pytest.raises(ValueError, match="unknown superseded decision"):
        ledger.append(
            session_id="s",
            decision_id="d2",
            domain="school",
            action="practice",
            predecessors=("d1",),
            supersedes="missing",
            disposition=DecisionDisposition.ACCEPTED,
        )


def test_supersession_tampering_breaks_hash_chain() -> None:
    ledger = make_ledger()
    ledger.supersede("d1", replacement_id="d2")
    ledger.records[1] = ledger.records[1].__class__(
        **{**ledger.records[1].__dict__, "supersedes": None}
    )
    with pytest.raises(ValueError, match="hash mismatch"):
        ledger.verify()
