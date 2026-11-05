"""Tests for #807 B032 (project memory planes)."""
from __future__ import annotations

import hashlib

import pytest

from skeleton.gameforge.batch_b032 import MemoryError_, MemoryPlane as P, PlaneScope, ProjectMemoryPlanes

S = PlaneScope("t1", "proj", "internal")


def mem():
    return ProjectMemoryPlanes(S)


def ev(m, key="obs", value="fps=60", tick=0):
    return m.write(S, P.EVIDENCE, key, value, source_id="run1", tick=tick,
                   content_digest=hashlib.sha256(value.encode()).hexdigest())


def test_planes_are_separately_retrievable():
    m = mem()
    m.write(S, P.DESIGN, "genre", "roguelike", source_id="doc", tick=0)
    m.write(S, P.EPHEMERAL, "cursor", "line 4", source_id="ui", tick=0)
    ev(m)
    assert [e.key for e in m.live(P.DESIGN)] == ["genre"]
    assert [e.key for e in m.live(P.EPHEMERAL)] == ["cursor"]
    assert [e.key for e in m.live(P.EVIDENCE)] == ["obs"]
    assert m.live(P.DECISION) == []


def test_cross_boundary_write_denied_and_audited():
    m = mem()
    with pytest.raises(MemoryError_, match="cross-boundary"):
        m.write(PlaneScope("t2", "proj", "internal"), P.DESIGN, "k", "v", source_id="s", tick=0)
    assert m.audit[-1][1] == "deny"


def test_evidence_requires_digest_and_is_append_only():
    m = mem()
    with pytest.raises(MemoryError_, match="sha256"):
        m.write(S, P.EVIDENCE, "k", "v", source_id="s", tick=0, content_digest="0" * 64)
    e = ev(m)
    with pytest.raises(MemoryError_, match="append-only"):
        m.write(S, P.EVIDENCE, "obs", "fps=30", source_id="s", tick=1, supersedes=e.entry_id,
                content_digest=hashlib.sha256(b"fps=30").hexdigest())


def test_design_supersession_keeps_history():
    m = mem()
    a = m.write(S, P.DESIGN, "genre", "roguelike", source_id="doc", tick=0)
    with pytest.raises(MemoryError_, match="supersede it explicitly"):
        m.write(S, P.DESIGN, "genre", "platformer", source_id="doc", tick=1)
    b = m.write(S, P.DESIGN, "genre", "platformer", source_id="doc", tick=1, supersedes=a.entry_id)
    assert m.get(P.DESIGN, "genre").value == "platformer"
    assert [e.entry_id for e in m.history(b.entry_id)] == [a.entry_id, b.entry_id]
    with pytest.raises(MemoryError_, match="already superseded"):
        m.write(S, P.DESIGN, "genre", "x", source_id="doc", tick=2, supersedes=a.entry_id)


def test_supersession_must_keep_key_and_plane():
    m = mem()
    a = m.write(S, P.DESIGN, "genre", "roguelike", source_id="doc", tick=0)
    with pytest.raises(MemoryError_, match="keep the key"):
        m.write(S, P.DESIGN, "other", "v", source_id="doc", tick=1, supersedes=a.entry_id)
    with pytest.raises(MemoryError_, match="same plane"):
        m.write(S, P.EPHEMERAL, "genre", "v", source_id="doc", tick=1, supersedes=a.entry_id)


def test_decisions_need_citations_and_rationale():
    m = mem()
    with pytest.raises(MemoryError_, match="must cite"):
        m.write(S, P.DECISION, "engine", "godot", source_id="lead", tick=0)
    eph = m.write(S, P.EPHEMERAL, "scratch", "x", source_id="ui", tick=0)
    with pytest.raises(MemoryError_, match="not a known evidence"):
        m.write(S, P.DECISION, "engine", "godot", source_id="lead", tick=0, cites=[eph.entry_id])
    e = ev(m)
    d = m.write(S, P.DECISION, "engine", "godot", source_id="lead", tick=0, cites=[e.entry_id])
    assert m.decision_support(d.entry_id) == [e]
    with pytest.raises(MemoryError_, match="rationale"):
        m.write(S, P.DECISION, "engine", "unity", source_id="lead", tick=1, cites=[e.entry_id],
                supersedes=d.entry_id)
    d2 = m.write(S, P.DECISION, "engine", "bevy", source_id="lead", tick=1, cites=[e.entry_id],
                 supersedes=d.entry_id, rationale="perf eval")
    assert m.get(P.DECISION, "engine") == d2


def test_ephemeral_ttl_expiry():
    m = mem()
    m.write(S, P.EPHEMERAL, "cursor", "a", source_id="ui", tick=0)
    assert m.get(P.EPHEMERAL, "cursor", tick=63) is not None
    assert m.get(P.EPHEMERAL, "cursor", tick=64) is None
    assert m.expire(64) == 1
    assert m.audit[-1][1] == "expire"
    m.write(S, P.EPHEMERAL, "cursor", "b", source_id="ui", tick=64)
    assert m.get(P.EPHEMERAL, "cursor", tick=64).value == "b"


def test_stale_decision_detected_when_cited_design_changes():
    m = mem()
    g = m.write(S, P.DESIGN, "players", "4", source_id="doc", tick=0)
    d = m.write(S, P.DECISION, "netcode", "rollback", source_id="lead", tick=0, cites=[g.entry_id])
    assert m.stale_decisions() == []
    m.write(S, P.DESIGN, "players", "64", source_id="doc", tick=1, supersedes=g.entry_id)
    assert m.stale_decisions() == [d]


def test_monotonic_ticks_and_input_validation():
    m = mem()
    m.write(S, P.DESIGN, "a", "v", source_id="s", tick=5)
    with pytest.raises(MemoryError_, match="monotonic"):
        m.write(S, P.DESIGN, "b", "v", source_id="s", tick=4)
    for bad in ("", "x\x00"):
        with pytest.raises(MemoryError_):
            m.write(S, P.DESIGN, bad, "v", source_id="s", tick=6)
    with pytest.raises(MemoryError_):
        m.write(S, P.DESIGN, "c", "v", source_id="s", tick=True)


def test_search_and_deterministic_ids():
    a, b = mem(), mem()
    for m in (a, b):
        m.write(S, P.DESIGN, "boss", "Dragon of ash", source_id="doc", tick=0, tags=["combat"])
        m.write(S, P.DESIGN, "hub", "Village", source_id="doc", tick=0, tags=["world"])
    assert [e.key for e in a.search(P.DESIGN, tag="combat")] == ["boss"]
    assert [e.key for e in a.search(P.DESIGN, text="village")] == ["hub"]
    assert a.snapshot_digest() == b.snapshot_digest()


def test_empty_scope_rejected():
    with pytest.raises(MemoryError_):
        PlaneScope("", "p", "t")
