"""Regression for the P0-P3 milestone modules."""
from __future__ import annotations

import pytest

from skeleton.jeeves.game_frontier_dynamics import PresentationClock
from skeleton.jeeves.game_frontier_p0_runtime import admit_p0_runtime, P0AdmissionError
from skeleton.jeeves.game_frontier_p1_worldmodel import WorldModelEvidence, world_model_receipt, P1WorldModelError
from skeleton.jeeves.game_frontier_p2_cognition import reason_cinematic, P2CognitionError
from skeleton.jeeves.game_frontier_p3_harness import qualify, P3QualificationError


def test_p0_admits_valid_clock():
    clock = PresentationClock(fps=60)
    receipt = admit_p0_runtime(
        clock,
        lod_tier=2,
        weather_digest="a" * 64,
        cognition_digest="b" * 64,
    )
    assert receipt.clock_fps == 60
    assert len(receipt.admission_id) == 64


def test_p0_rejects_bad_clock():
    with pytest.raises(P0AdmissionError):
        admit_p0_runtime(
            PresentationClock(fps=60),
            lod_tier=9,
            weather_digest="a" * 64,
            cognition_digest="b" * 64,
        )


def test_p1_receipt_is_stable():
    evidence = WorldModelEvidence(
        source_digest="c" * 64,
        mesh_vertex_count=1200,
        mesh_triangle_count=800,
        reconstruction_digest="d" * 64,
        adapter_id="candidate-recon-v1",
    )
    a = world_model_receipt(evidence)
    b = world_model_receipt(evidence)
    assert a == b
    assert len(a) == 64


def test_p1_rejects_empty_mesh():
    with pytest.raises(P1WorldModelError):
        WorldModelEvidence(
            source_digest="c" * 64,
            mesh_vertex_count=1,
            mesh_triangle_count=0,
            reconstruction_digest="d" * 64,
            adapter_id="x",
        )


def test_p2_is_deterministic():
    a = reason_cinematic(("ridge", "wind", "path"), goal="reach-summit")
    b = reason_cinematic(("ridge", "wind", "path"), goal="reach-summit")
    assert a == b
    assert a.action in {"observe", "approach", "hold", "retreat"}
    assert 0.0 <= a.confidence <= 1.0


def test_p2_rejects_empty():
    with pytest.raises(P2CognitionError):
        reason_cinematic((), goal="x")


def test_p3_binds_receipts():
    p0 = admit_p0_runtime(
        PresentationClock(fps=30),
        lod_tier=1,
        weather_digest="a" * 64,
        cognition_digest="b" * 64,
    )
    p1 = world_model_receipt(
        WorldModelEvidence(
            source_digest="c" * 64,
            mesh_vertex_count=10,
            mesh_triangle_count=4,
            reconstruction_digest="d" * 64,
            adapter_id="v1",
        )
    )
    p2 = reason_cinematic(("a",), goal="hold")
    qual = qualify(p0_admission_id=p0.admission_id, p1_receipt=p1, p2_receipt_id=p2.receipt_id)
    assert qual.claim == "candidate-only"
    assert len(qual.qualification_id) == 64


def test_p3_rejects_short_id():
    with pytest.raises(P3QualificationError):
        qualify(p0_admission_id="abc", p1_receipt="d" * 64, p2_receipt_id="e" * 64)
