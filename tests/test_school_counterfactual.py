from skeleton.school.counterfactual import CandidateAction, PolicyCandidate, compete, default_candidates


def test_competition_is_deterministic() -> None:
    result = compete(default_candidates(mastery=0.9, contradiction=0.0, energy=0.9, transfer_ready=True))
    assert result.selected.action in {CandidateAction.TRANSFER, CandidateAction.CHALLENGE}
    assert result.margin >= 0.0


def test_contradiction_favors_repair() -> None:
    result = compete(default_candidates(mastery=0.95, contradiction=1.0, energy=0.9, transfer_ready=True))
    assert result.selected.action is CandidateAction.REPAIR
    assert any(candidate.action is CandidateAction.CHALLENGE for candidate in result.rejected)


def test_low_energy_favors_pause() -> None:
    result = compete(default_candidates(mastery=0.9, contradiction=0.0, energy=0.05, transfer_ready=True))
    assert result.selected.action is CandidateAction.PAUSE
