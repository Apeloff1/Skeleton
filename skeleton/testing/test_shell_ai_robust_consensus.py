"""Unique-model/provider consensus safety tests."""

from __future__ import annotations

import pytest

from skeleton.shells.ai.robust_consensus import (
    ConsensusPolicy,
    RobustProposalConsensus,
)
from skeleton.shells.ai.types import AIAction, AIPlanProposal


def proposal(
    proposal_id,
    model_id,
    *,
    command="python",
    args=("-V",),
    confidence=0.9,
    uncertainty=0.1,
):
    return AIPlanProposal(
        proposal_id,
        "i",
        (AIAction("a", command, args),),
        confidence=confidence,
        uncertainty=uncertainty,
        model_id=model_id,
    )


def test_duplicate_same_model_counts_one_vote():
    consensus = RobustProposalConsensus(
        ConsensusPolicy(min_unique_models=2)
    )
    report = consensus.evaluate(
        (
            proposal("p1", "model-a"),
            proposal("p2", "model-a"),
        )
    )
    assert not report.reached
    assert report.groups[0].unique_model_votes == 1


def test_two_unique_models_can_reach_consensus():
    consensus = RobustProposalConsensus(
        ConsensusPolicy(min_unique_models=2)
    )
    report = consensus.evaluate(
        (
            proposal("p1", "model-a"),
            proposal("p2", "model-b"),
        )
    )
    assert report.reached
    assert report.groups[0].unique_model_votes == 2


def test_different_shapes_do_not_agree():
    consensus = RobustProposalConsensus(
        ConsensusPolicy(min_unique_models=2)
    )
    report = consensus.evaluate(
        (
            proposal("p1", "model-a", args=("-V",)),
            proposal("p2", "model-b", args=("--help",)),
        )
    )
    assert not report.reached
    assert len(report.groups) == 2


def test_provider_diversity_requirement():
    consensus = RobustProposalConsensus(
        ConsensusPolicy(
            min_unique_models=2,
            min_unique_providers=2,
        )
    )
    proposals = (
        proposal("p1", "model-a"),
        proposal("p2", "model-b"),
    )
    same = consensus.evaluate(
        proposals,
        provider_by_model={
            "model-a": "provider-one",
            "model-b": "provider-one",
        },
    )
    assert not same.reached
    diverse = consensus.evaluate(
        proposals,
        provider_by_model={
            "model-a": "provider-one",
            "model-b": "provider-two",
        },
    )
    assert diverse.reached


def test_missing_provider_can_be_rejected():
    consensus = RobustProposalConsensus(
        ConsensusPolicy(
            min_unique_models=2,
            min_unique_providers=1,
            reject_missing_provider_id=True,
        )
    )
    report = consensus.evaluate(
        (
            proposal("p1", "model-a"),
            proposal("p2", "model-b"),
        ),
        provider_by_model={"model-a": "one"},
    )
    assert not report.reached
    assert any(
        "provider identity missing" in reason
        for reason in report.groups[0].reasons
    )


def test_missing_model_is_ignored_by_default():
    consensus = RobustProposalConsensus(
        ConsensusPolicy(min_unique_models=1)
    )
    report = consensus.evaluate(
        (proposal("p1", ""),)
    )
    assert not report.reached
    assert report.groups == ()


def test_missing_model_can_be_anonymous_vote_when_allowed():
    consensus = RobustProposalConsensus(
        ConsensusPolicy(
            min_unique_models=1,
            reject_missing_model_id=False,
        )
    )
    report = consensus.evaluate(
        (proposal("p1", ""),)
    )
    assert report.reached
    assert report.groups[0].unique_model_votes == 1


def test_confidence_floor():
    consensus = RobustProposalConsensus(
        ConsensusPolicy(
            min_unique_models=2,
            min_average_confidence=0.8,
        )
    )
    report = consensus.evaluate(
        (
            proposal("p1", "a", confidence=0.7),
            proposal("p2", "b", confidence=0.7),
        )
    )
    assert not report.reached
    assert any("confidence" in reason for reason in report.groups[0].reasons)


def test_uncertainty_ceiling():
    consensus = RobustProposalConsensus(
        ConsensusPolicy(
            min_unique_models=2,
            max_average_uncertainty=0.2,
        )
    )
    report = consensus.evaluate(
        (
            proposal("p1", "a", uncertainty=0.3),
            proposal("p2", "b", uncertainty=0.3),
        )
    )
    assert not report.reached
    assert any("uncertainty" in reason for reason in report.groups[0].reasons)


def test_same_model_best_proposal_is_retained():
    consensus = RobustProposalConsensus(
        ConsensusPolicy(min_unique_models=1)
    )
    report = consensus.evaluate(
        (
            proposal(
                "low",
                "a",
                confidence=0.5,
                uncertainty=0.5,
            ),
            proposal(
                "high",
                "a",
                confidence=0.9,
                uncertainty=0.1,
            ),
        )
    )
    assert report.reached
    assert report.groups[0].proposal_ids == ("high",)
    assert report.groups[0].average_confidence == 0.9


def test_eligible_group_beats_ineligible_larger_group():
    consensus = RobustProposalConsensus(
        ConsensusPolicy(
            min_unique_models=2,
            min_unique_providers=2,
        )
    )
    proposals = (
        proposal("a1", "a1", args=("one",)),
        proposal("a2", "a2", args=("one",)),
        proposal("a3", "a3", args=("one",)),
        proposal("b1", "b1", args=("two",)),
        proposal("b2", "b2", args=("two",)),
    )
    report = consensus.evaluate(
        proposals,
        provider_by_model={
            "a1": "one",
            "a2": "one",
            "a3": "one",
            "b1": "one",
            "b2": "two",
        },
    )
    assert report.reached
    winning = next(
        group
        for group in report.groups
        if group.shape_digest == report.winning_shape
    )
    assert set(winning.model_ids) == {"b1", "b2"}


def test_report_is_deterministic_under_input_order():
    consensus = RobustProposalConsensus(
        ConsensusPolicy(min_unique_models=2)
    )
    items = (
        proposal("p1", "a"),
        proposal("p2", "b"),
    )
    first = consensus.evaluate(items)
    second = consensus.evaluate(tuple(reversed(items)))
    assert first.winning_shape == second.winning_shape
    assert first.to_dict() == second.to_dict()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"min_unique_models": 0},
        {"min_unique_providers": 0},
        {"min_average_confidence": -0.1},
        {"min_average_confidence": 1.1},
        {"max_average_uncertainty": -0.1},
        {"max_average_uncertainty": 1.1},
    ],
)
def test_consensus_policy_validation(kwargs):
    with pytest.raises(ValueError):
        ConsensusPolicy(**kwargs)
