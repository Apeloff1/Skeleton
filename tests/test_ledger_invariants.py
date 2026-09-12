import pytest
from skeleton.school.decision_ledger import DecisionDisposition, DecisionLedger, EvidenceKind, EvidenceRef


def ledger():
    l = DecisionLedger()
    l.register_evidence(EvidenceRef("e", EvidenceKind.OBSERVATION, "s", "x"))
    l.append(session_id="s", decision_id="d1", domain="test", action="practice", evidence=("e",))
    return l


def test_supersession_is_single_use_and_filters_active_records():
    l = ledger()
    replacement = l.supersede("d1", replacement_id="d2")
    assert replacement.disposition is DecisionDisposition.ACCEPTED
    assert tuple(r.decision_id for r in l.active_records("s")) == ("d2",)
    with pytest.raises(ValueError, match="already superseded"):
        l.supersede("d1", replacement_id="d3")


def test_self_supersession_is_rejected():
    l = ledger()
    with pytest.raises(ValueError, match="cannot supersede itself"):
        l.supersede("d1", replacement_id="d1")


def test_supersession_replacement_id_must_be_unique():
    l = ledger()
    l.supersede("d1", replacement_id="d2")
    with pytest.raises(ValueError, match="duplicate decision id"):
        l.supersede("d2", replacement_id="d2")


def test_supersession_is_hash_chained_and_explainable():
    l = ledger()
    l.supersede("d1", replacement_id="d2")
    l.verify()
    assert l.records[-1].disposition is DecisionDisposition.ACCEPTED
    assert tuple(r.decision_id for r in l.explain("d2")) == ("d1", "d2")
