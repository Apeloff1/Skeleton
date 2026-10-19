"""Adversarial 100-capability milestone board: no completion by assertion."""

from dataclasses import replace

import pytest

from skeleton.jeeves.agent.delivery_assurance_milestones import (
    ASSURANCE_MILESTONES, MilestoneAttestation,
    MilestoneBoard, MilestoneEvidenceError, milestone_by_id,
    restore_milestone_board, verify_milestone_board,
)


COMMIT = "a" * 40


def evidence(code, *, source_commit=COMMIT, verdict="pass"):
    return MilestoneAttestation(
        milestone_id=code,
        source_commit=source_commit,
        artifact_digest="b" * 64,
        scope=f"host reviewed {code} on exact commit",
        primary_checker="ci-primary",
        independent_checker="review-secondary",
        primary_evidence=f"run:primary:{code}",
        independent_evidence=f"run:secondary:{code}",
        verdict=verdict,
    )


def test_catalog_has_exactly_one_hundred_distinct_capabilities():
    assert len(ASSURANCE_MILESTONES) == 100
    assert ASSURANCE_MILESTONES[0].code == "M001"
    assert ASSURANCE_MILESTONES[-1].code == "M100"
    assert len({m.capability for m in ASSURANCE_MILESTONES}) == 100
    assert len({m.domain for m in ASSURANCE_MILESTONES}) == 10
    assert all(m.prerequisite is None for m in ASSURANCE_MILESTONES[::10])
    assert milestone_by_id("M020").prerequisite == "M019"


def test_unverified_roadmap_does_not_claim_code_is_completed():
    board = MilestoneBoard.begin(COMMIT)
    summary = board.summary()
    assert board.target_count == 100
    assert board.completion_count == 0
    assert board.completion_percent == 0.0
    assert summary["unverified"] == 100
    assert summary["passed"] == 0
    assert len(board.fingerprint) == 64


def test_evidenced_progress_is_idempotent_and_monotonically_ordered():
    board = MilestoneBoard.begin(COMMIT)
    first = evidence("M001")
    board = board.register(first)
    assert board.register(first) is board
    board = board.register(evidence("M002"))
    assert board.completion_count == 2
    assert board.completion_percent == 2.0
    assert board.receipts[1].previous == board.receipts[0].digest
    assert board.summary()["unverified"] == 98
    verify_milestone_board(board)
    assert restore_milestone_board(COMMIT, board.receipts) == board


def test_source_commit_is_required_and_bound_to_every_attestation():
    with pytest.raises(MilestoneEvidenceError, match="pin exact"):
        MilestoneBoard.begin("")
    board = MilestoneBoard.begin(COMMIT)
    with pytest.raises(MilestoneEvidenceError, match="another commit"):
        board.register(evidence("M001", source_commit="c" * 40))
    with pytest.raises(MilestoneEvidenceError, match="exact source"):
        evidence("M001", source_commit="c")


def test_prerequisite_cannot_be_skipped_or_marked_pass_by_a_blocked_step():
    board = MilestoneBoard.begin(COMMIT)
    with pytest.raises(MilestoneEvidenceError, match="prerequisite"):
        board.register(evidence("M002"))
    board = board.register(evidence("M001", verdict="blocked"))
    assert board.completion_count == 0
    assert board.summary()["blocked"] == 1
    with pytest.raises(MilestoneEvidenceError, match="prerequisite"):
        board.register(evidence("M002"))
    with pytest.raises(MilestoneEvidenceError, match="changed"):
        board.register(evidence("M001"))


def test_parallel_domain_first_milestones_can_have_independent_progress():
    board = MilestoneBoard.begin(COMMIT)
    for index in range(1, 101, 10):
        board = board.register(evidence(f"M{index:03d}"))
    assert board.completion_count == 10
    assert board.summary()["unverified"] == 90
    verify_milestone_board(board)


def test_all_one_hundred_milestones_can_be_attested_in_order():
    board = MilestoneBoard.begin(COMMIT)
    for entry in ASSURANCE_MILESTONES:
        board = board.register(evidence(entry.code))
    assert board.completion_count == 100
    assert board.completion_percent == 100.0
    assert len(board.receipts) == 100
    verify_milestone_board(board)
    assert restore_milestone_board(COMMIT, board.receipts).fingerprint == board.fingerprint


@pytest.mark.parametrize("change", (
    {"milestone_id": "M999"},
    {"source_commit": "bad"},
    {"artifact_digest": "not-a-sha256"},
    {"scope": "  "},
    {"primary_checker": "bad "},
    {"independent_checker": "ci-primary"},
    {"primary_evidence": " "},
    {"independent_evidence": "run:primary:M001"},
    {"verdict": "success"},
))
def test_invalid_or_coupled_attestations_are_rejected(change):
    with pytest.raises(MilestoneEvidenceError):
        replace(evidence("M001"), **change)


@pytest.mark.parametrize("field,value", (
    ("digest", "0" * 64),
    ("previous", "1" * 64),
    ("sequence", 55),
    ("milestone_id", "M009"),
))
def test_tampering_hash_linked_receipt_is_rejected(field, value):
    board = MilestoneBoard.begin(COMMIT).register(evidence("M001"))
    changed = replace(board.receipts[0], **{field: value})
    with pytest.raises(MilestoneEvidenceError):
        restore_milestone_board(COMMIT, (changed,))


def test_forced_mutation_of_frozen_evidence_cannot_bypass_validation():
    board = MilestoneBoard.begin(COMMIT).register(evidence("M001"))
    forged = replace(board.receipts[0], attestation=replace(
        board.receipts[0].attestation, primary_checker="  ",
    ))
    with pytest.raises(MilestoneEvidenceError):
        restore_milestone_board(COMMIT, (forged,))


def test_duplicate_attestation_cannot_relabel_or_repeat_a_milestone():
    board = MilestoneBoard.begin(COMMIT).register(evidence("M001"))
    forged = replace(board.receipts[0], sequence=2)
    with pytest.raises(MilestoneEvidenceError):
        restore_milestone_board(COMMIT, (board.receipts[0], forged))
    with pytest.raises(MilestoneEvidenceError, match="changed"):
        board.register(replace(evidence("M001"), scope="different review"))


def test_blocked_milestones_are_explicit_and_never_count_as_pass():
    board = MilestoneBoard.begin(COMMIT)
    board = board.register(evidence("M001", verdict="blocked"))
    board = board.register(evidence("M011", verdict="pass"))
    summary = board.summary()
    assert summary["passed"] == 1
    assert summary["blocked"] == 1
    assert summary["unverified"] == 98


def test_future_evidence_and_unknown_milestones_fail_closed():
    with pytest.raises(MilestoneEvidenceError, match="unknown"):
        milestone_by_id("M101")
    with pytest.raises(MilestoneEvidenceError, match="unknown"):
        milestone_by_id(None)
    with pytest.raises(MilestoneEvidenceError, match="unknown"):
        evidence("M000")
