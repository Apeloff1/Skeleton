"""Regression for frontier composition and durable replay."""
from __future__ import annotations

import pytest

from skeleton.jeeves.game_frontier_dynamics import PresentationClock
from skeleton.jeeves.game_frontier_p1_worldmodel import WorldModelEvidence
from skeleton.jeeves.game_frontier_milestone_compose import compose_frontier
from skeleton.jeeves.game_frontier_replay import replay_from, ReplayError


def _evidence() -> WorldModelEvidence:
    return WorldModelEvidence(
        source_digest="a" * 64,
        mesh_vertex_count=100,
        mesh_triangle_count=40,
        reconstruction_digest="b" * 64,
        adapter_id="compose-v1",
    )


def test_compose_is_deterministic():
    clock = PresentationClock(fps=60)
    a = compose_frontier(
        clock=clock, lod_tier=2, weather_digest="c" * 64,
        evidence=_evidence(), percepts=("ridge", "wind"), goal="summit",
    )
    clock2 = PresentationClock(fps=60)
    b = compose_frontier(
        clock=clock2, lod_tier=2, weather_digest="c" * 64,
        evidence=_evidence(), percepts=("ridge", "wind"), goal="summit",
    )
    assert a.admission_digest == b.admission_digest
    assert a.p3.claim == "candidate-only"


def test_compose_binds_all_stages():
    admission = compose_frontier(
        clock=PresentationClock(fps=30), lod_tier=1, weather_digest="d" * 64,
        evidence=_evidence(), percepts=("path",), goal="hold",
    )
    assert len(admission.p0.admission_id) == 64
    assert len(admission.p1_receipt) == 64
    assert len(admission.p2.receipt_id) == 64
    assert len(admission.p3.qualification_id) == 64


def test_replay_chain_verifies():
    admission = compose_frontier(
        clock=PresentationClock(fps=50), lod_tier=0, weather_digest="e" * 64,
        evidence=_evidence(), percepts=("a", "b"), goal="observe",
    )
    log = replay_from("session-1", [admission.admission_digest, "f" * 64])
    assert log.verify()
    assert len(log.entries) == 2
    assert len(log.head) == 64


def test_replay_rejects_bad_digest():
    with pytest.raises(ReplayError):
        replay_from("s", ["not-a-digest"])


def test_replay_detects_tamper():
    log = replay_from("s", ["a" * 64, "b" * 64])
    log.entries[0] = "c" * 64
    assert log.verify() is False
