from skeleton.frontier.assurance.decision import Decision


def test_decision_defaults_evidence_per_instance():
    first = Decision("admit", True, "verified")
    second = Decision("reject", False, "gate")
    assert first.evidence == {}
    assert second.evidence == {}
    assert first.evidence is not second.evidence
