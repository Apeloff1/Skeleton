from skeleton.frontier.gameforge_outcome import Outcome, OutcomeKind

def test_outcome_is_immutable_and_normalized():
    outcome = Outcome(OutcomeKind.COMPLETED, "req-1", "ok")
    assert outcome.kind.value == "completed"
    assert outcome.request_id == "req-1"
