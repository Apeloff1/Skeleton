"""Boardroom sessions / motions — port of gameforge-rs boardroom.rs."""

from __future__ import annotations

import pytest

from skeleton.swarm.boardroom import (
    Boardroom,
    MotionStatus,
    Session,
)


@pytest.fixture()
def room() -> Boardroom:
    return Boardroom()


def test_convene_opens_session(room: Boardroom):
    session = room.convene("Q3 strategy", "chair-alice", ["budget", "hiring"])
    assert isinstance(session, Session)
    assert session.title == "Q3 strategy"
    assert session.chair == "chair-alice"
    assert session.agenda == ["budget", "hiring"]
    assert session.closed is None
    assert session.id
    assert len(room.sessions()) == 1


def test_table_motion_in_open_session(room: Boardroom):
    session = room.convene("sit", "bob", ["item-1"])
    result = room.table_motion(session.id, "alice", "Approve LAFS port")
    assert result is not None
    motion, proposal_id = result
    assert motion.session_id == session.id
    assert motion.mover == "alice"
    assert motion.text == "Approve LAFS port"
    assert motion.status is MotionStatus.TABLED
    assert motion.resolution_event is None
    assert proposal_id == f"motion:{motion.id}"
    assert len(room.session_motions(session.id)) == 1


def test_table_motion_rejects_closed_or_unknown(room: Boardroom):
    session = room.convene("sit", "bob", [])
    room.adjourn(session.id)
    assert room.table_motion(session.id, "alice", "too late") is None
    assert room.table_motion("no-such-session", "alice", "ghost") is None


def test_resolve_motion_carried_with_fabric_event(room: Boardroom):
    session = room.convene("sit", "bob", [])
    motion, _ = room.table_motion(session.id, "alice", "Ship boardroom")
    fabric_event = "merkle:evt-deadbeef"
    resolved = room.resolve_motion(motion.id, True, event_id=fabric_event)
    assert resolved is not None
    assert resolved.status is MotionStatus.RESOLVED
    assert resolved.resolution_event == fabric_event


def test_resolve_motion_rejected(room: Boardroom):
    session = room.convene("sit", "bob", [])
    motion, _ = room.table_motion(session.id, "alice", "No")
    rejected = room.resolve_motion(motion.id, False, event_id="merkle:evt-01")
    assert rejected is not None
    assert rejected.status is MotionStatus.REJECTED
    assert rejected.resolution_event == "merkle:evt-01"


def test_resolve_motion_idempotent_refuse(room: Boardroom):
    session = room.convene("sit", "bob", [])
    motion, _ = room.table_motion(session.id, "alice", "Once")
    assert room.resolve_motion(motion.id, True, event_id="e1") is not None
    assert room.resolve_motion(motion.id, False, event_id="e2") is None
    assert room.resolve_motion("missing", True) is None


def test_adjourn_closes_session(room: Boardroom):
    session = room.convene("sit", "bob", ["a"])
    closed = room.adjourn(session.id)
    assert closed is not None
    assert closed.closed is not None
    assert room.adjourn(session.id) is None  # already closed


def test_session_motions_and_sessions_lists(room: Boardroom):
    s1 = room.convene("A", "c1", [])
    s2 = room.convene("B", "c2", [])
    room.table_motion(s1.id, "m1", "one")
    room.table_motion(s1.id, "m2", "two")
    room.table_motion(s2.id, "m3", "three")
    assert len(room.session_motions(s1.id)) == 2
    assert len(room.session_motions(s2.id)) == 1
    titles = {s.title for s in room.sessions()}
    assert titles == {"A", "B"}
