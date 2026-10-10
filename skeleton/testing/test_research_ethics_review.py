import pytest
from skeleton.eval.research_ethics import *


def test_technical_success_cannot_substitute_for_review():
    review = EthicsReview(
        "r",
        ResearchRisk(True, False, False),
        False,
        None,
    )
    assert not decide(review).approved


def test_sensitive_research_requires_oversight():
    review = EthicsReview(
        "r",
        ResearchRisk(False, True, False),
        True,
        None,
    )
    assert not decide(review).approved


def test_nonboolean_risk_assertion_rejected_at_boundary():
    with pytest.raises(ValueError):
        ResearchRisk(1, False, False)


def test_sensitive_review_requires_consent_and_oversight():
    risk = ResearchRisk(False, False, True)
    assert not decide(EthicsReview("r1", risk, False, "board")).approved
    assert not decide(EthicsReview("r2", risk, True, None)).approved
    assert decide(EthicsReview("r3", risk, True, "board")).approved


def test_nonsensitive_review_does_not_invent_external_oversight_requirement():
    review = EthicsReview(
        "r",
        ResearchRisk(False, False, False),
        False,
        None,
    )
    assert decide(review).approved
