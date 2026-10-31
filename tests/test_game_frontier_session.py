"""Regression for the frontier session orchestrator."""
from __future__ import annotations

import pytest

from skeleton.jeeves.game_frontier_dynamics import PresentationClock
from skeleton.jeeves.game_frontier_p1_worldmodel import WorldModelEvidence
from skeleton.jeeves.game_frontier_session import FrontierSession, SessionError


def _evidence(tag: str = "a") -> WorldModelEvidence:
    return WorldModelEvidence(
        source_digest=tag * 64,
        mesh_vertex_count=50,
        mesh_triangle_count=20,
        reconstruction_digest="b" * 64,
        adapter_id="session-v1",
    )


def test_session_records_steps():
    session = FrontierSession(session_id="run-1")
    session.step(
        clock=PresentationClock(fps=60), lod_tier=1, weather_digest="c" * 64,
        evidence=_evidence(), percepts=("ridge",), goal="summit",
    )
    session.step(
        clock=PresentationClock(fps=30), lod_tier=2, weather_digest="d" * 64,
        evidence=_evidence("e"), percepts=("path", "wind"), goal="hold",
    )
    assert len(session.admissions) == 2
    assert session.verify()
    assert len(session.head) == 64


def test_session_rejects_empty_id():
    with pytest.raises(SessionError):
        FrontierSession(session_id="")


def test_empty_session_does_not_verify():
    session = FrontierSession(session_id="empty")
    assert session.verify() is False


def test_steps_are_deterministic():
    a = FrontierSession(session_id="a")
    b = FrontierSession(session_id="b")
    kwargs = dict(
        clock=PresentationClock(fps=50), lod_tier=0, weather_digest="f" * 64,
        evidence=_evidence(), percepts=("x",), goal="observe",
    )
    a.step(**kwargs)
    b.step(**kwargs)
    assert a.admissions[0].admission_digest == b.admissions[0].admission_digest
