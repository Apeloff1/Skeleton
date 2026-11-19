from skeleton.frontier.assurance import BoundedInt, Decision, Outcome, QualityGate, Snapshot, Verification


def test_assurance_contracts_compose():
    budget = BoundedInt(2, 0, 4)
    decision = Decision("admit", True, "within budget")
    gate = QualityGate.from_checks([budget.value <= budget.maximum, decision.allowed])
    verification = Verification("artifact", gate.passed, ("bounds", "admission"))
    snapshot = Snapshot.capture(1, {"decision": decision.action, "budget": budget.value})
    outcome = Outcome(value=snapshot.digest)
    verification.require()
    assert outcome.ok
