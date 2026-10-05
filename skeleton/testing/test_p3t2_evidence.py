from __future__ import annotations

import hashlib

import pytest

from skeleton.ai.runtime.p3t2 import (
    P3T2ContinuationReceipt,
    P3T2EvidenceError,
    P3T2LaneProof,
    P3T2LaneReceipt,
)


REVISION = "a" * 40
SUBJECT = "p3t2-fixture"


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def proof(task: str, lane: str, volume: str, *, revision: str = REVISION, producer: str = "builder", verifier: str = "independent-verifier") -> P3T2LaneProof:
    return P3T2LaneProof(
        task_id=task,
        lane_id=lane,
        volume_ref=volume,
        execution_subject=SUBJECT,
        source_revision=revision,
        producer_id=producer,
        verifier_id=verifier,
        evidence_refs=(f"pytest:{volume}",),
        observation_digest=digest(volume),
    )


def lane(task: str, lane_id: str, volumes: tuple[str, ...], dependencies: tuple[str, ...] = ()) -> P3T2LaneReceipt:
    return P3T2LaneReceipt(
        task_id=task,
        lane_id=lane_id,
        expected_volume_refs=volumes,
        proofs=tuple(proof(task, lane_id, volume) for volume in volumes),
        dependency_receipt_digests=dependencies,
    )


def test_lane_receipt_requires_exact_volume_union() -> None:
    with pytest.raises(P3T2EvidenceError, match="coverage mismatch"):
        P3T2LaneReceipt(
            task_id="P3T2-TRAINING-01",
            lane_id="P3T2-L2",
            expected_volume_refs=("VOL-143", "VOL-144"),
            proofs=(proof("P3T2-TRAINING-01", "P3T2-L2", "VOL-143"),),
        )


def test_lane_receipt_rejects_cross_revision_stitching() -> None:
    with pytest.raises(P3T2EvidenceError, match="one exact source revision"):
        P3T2LaneReceipt(
            task_id="P3T2-TRAINING-01",
            lane_id="P3T2-L2",
            expected_volume_refs=("VOL-143", "VOL-144"),
            proofs=(
                proof("P3T2-TRAINING-01", "P3T2-L2", "VOL-143"),
                proof("P3T2-TRAINING-01", "P3T2-L2", "VOL-144", revision="b" * 40),
            ),
        )


def test_self_verification_is_rejected() -> None:
    with pytest.raises(P3T2EvidenceError, match="independent"):
        proof(
            "P3T2-LEARNING-01",
            "P3T2-L3",
            "VOL-150",
            producer="same-agent",
            verifier="same-agent",
        )


def test_dependency_chain_is_digest_bound() -> None:
    training = lane(
        "P3T2-TRAINING-01",
        "P3T2-L2",
        ("VOL-143", "VOL-144"),
    )
    learning = lane(
        "P3T2-LEARNING-01",
        "P3T2-L3",
        ("VOL-150",),
        (training.digest,),
    )
    receipt = P3T2ContinuationReceipt(
        receipts=(training, learning),
        required_dependencies={
            "P3T2-TRAINING-01": (),
            "P3T2-LEARNING-01": ("P3T2-TRAINING-01",),
        },
    )
    assert receipt.source_revision == REVISION
    assert receipt.execution_subject == SUBJECT
    assert receipt.as_dict()["promotion_authority"] is False
    assert len(receipt.digest) == 64


def test_wrong_dependency_digest_fails_closed() -> None:
    training = lane(
        "P3T2-TRAINING-01",
        "P3T2-L2",
        ("VOL-143",),
    )
    learning = lane(
        "P3T2-LEARNING-01",
        "P3T2-L3",
        ("VOL-150",),
        (digest("wrong"),),
    )
    with pytest.raises(P3T2EvidenceError, match="dependency digest chain mismatch"):
        P3T2ContinuationReceipt(
            receipts=(training, learning),
            required_dependencies={
                "P3T2-TRAINING-01": (),
                "P3T2-LEARNING-01": ("P3T2-TRAINING-01",),
            },
        )


def test_digest_is_order_stable_for_proofs() -> None:
    first = P3T2LaneReceipt(
        task_id="P3T2-TRAINING-01",
        lane_id="P3T2-L2",
        expected_volume_refs=("VOL-143", "VOL-144"),
        proofs=(
            proof("P3T2-TRAINING-01", "P3T2-L2", "VOL-143"),
            proof("P3T2-TRAINING-01", "P3T2-L2", "VOL-144"),
        ),
    )
    second = P3T2LaneReceipt(
        task_id="P3T2-TRAINING-01",
        lane_id="P3T2-L2",
        expected_volume_refs=("VOL-143", "VOL-144"),
        proofs=tuple(reversed(first.proofs)),
    )
    assert first.digest == second.digest
