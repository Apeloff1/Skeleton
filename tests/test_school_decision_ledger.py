from skeleton.school.decision_ledger import (
    DecisionDisposition,
    DecisionLedger,
    EvidenceKind,
    EvidenceRef,
    evidence_bundle,
)


def test_ledger_hash_chain_and_causal_explanation() -> None:
    ledger = DecisionLedger()
    ledger.register_evidence(EvidenceRef("e1", EvidenceKind.ASSESSMENT, "skill:x", "score", 0.9))
    ledger.append(
        session_id="s1",
        decision_id="d1",
        domain="assessment",
        action="teach",
        rationale=("mastery gap",),
        evidence=("e1",),
        state={"mastery": 0.3},
        policy={"threshold": 0.7},
        disposition=DecisionDisposition.ACCEPTED,
    )
    ledger.append(
        session_id="s1",
        decision_id="d2",
        domain="session",
        action="practice",
        predecessors=("d1",),
        evidence=("e1",),
    )
    ledger.verify()
    assert [record.decision_id for record in ledger.explain("d2")] == ["d1", "d2"]


def test_supersession_creates_explicit_causal_record() -> None:
    ledger = DecisionLedger()
    ledger.register_evidence(EvidenceRef("e1", EvidenceKind.OBSERVATION, "energy", "normal"))
    ledger.append(session_id="s1", decision_id="d1", domain="energy", action="deep_work", evidence=("e1",))
    replacement = ledger.supersede("d1", replacement_id="d2")
    assert replacement.disposition is DecisionDisposition.ACCEPTED
    assert replacement.predecessors == ("d1",)
    ledger.verify()


def test_evidence_bundle_is_canonical() -> None:
    items = [
        EvidenceRef("b", EvidenceKind.SYSTEM, "x", "b"),
        EvidenceRef("a", EvidenceKind.SYSTEM, "x", "a"),
    ]
    assert [item.evidence_id for item in evidence_bundle(items)] == ["a", "b"]
