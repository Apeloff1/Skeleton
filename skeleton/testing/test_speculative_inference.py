import pytest
from skeleton.ai.speculative_inference import *


def test_draft_token_never_accepted_without_target_match():
    steps = verify(
        SpeculativePlan("d", "t", 2),
        (DraftToken(1, 0.9), DraftToken(2, 0.9)),
        (1, 3),
    )
    assert accepted_tokens(steps) == (1,)
    assert not steps[-1].accepted


def test_target_verification_is_explicit():
    step = verify(
        SpeculativePlan("d", "t", 1),
        (DraftToken(1, 1.0),),
        (1,),
    )[0]
    assert step.target_token == 1


def test_target_must_verify_every_attempted_draft():
    plan = SpeculativePlan("d", "t", 2)
    with pytest.raises(ValueError):
        verify(plan, (DraftToken(1, 0.5), DraftToken(2, 0.5)), (1,))


def test_max_tokens_bounds_verification():
    assert len(
        verify(
            SpeculativePlan("d", "t", 1),
            (DraftToken(1, 0.5), DraftToken(2, 0.5)),
            (1, 2),
        )
    ) == 1


def test_fallback_policy_and_target_types_fail_closed():
    with pytest.raises(ValueError):
        SpeculativePlan("d", "t", 1, fallback=1)
    with pytest.raises(ValueError):
        verify(SpeculativePlan("d", "t", 1), (DraftToken(1, 0.5),), (True,))


def test_rejection_requires_fallback_when_enabled():
    plan = SpeculativePlan("d", "t", 2, fallback=True)
    drafts = (DraftToken(1, 0.5), DraftToken(2, 0.5))
    steps = verify(plan, drafts, (1, 3))
    assert fallback_required(plan, steps, drafts)
