"""Tests for #807 B035 (narrative planner and canon graph)."""
from __future__ import annotations

import pytest

from skeleton.gameforge.batch_b032 import MemoryPlane, PlaneScope, ProjectMemoryPlanes
from skeleton.gameforge.batch_b035 import Arc, Beat, CanonError, CanonGraph, Effect as E, NarrativePlan


def canon():
    g = CanonGraph()
    g.add_entity("hero", "character")
    g.add_entity("mentor", "character")
    g.add_entity("sword", "item", owner="mentor")
    g.relate("mentor", "teaches", "hero")
    g.forbid("hero", "status", "dead")
    return g


B1 = Beat("b1", "main", ("hero", "mentor"), effects=(E("sword", "owner", "hero"),))
B2 = Beat("b2", "main", ("mentor",), effects=(E("mentor", "status", "dead"),))
B3 = Beat("b3", "main", ("hero",), requires=(E("sword", "owner", "hero"),))
ARC = Arc("main", ("b1", "b2", "b3"))


def story():
    return NarrativePlan((B1, B2, B3), (ARC,))


def test_valid_story_and_consequences():
    assert story().validate(canon()) == []
    assert story().consequences(canon()) == {("sword", "owner"): "hero", ("mentor", "status"): "dead"}


def test_dead_participant_detected():
    late = Beat("b4", "main", ("mentor",))
    v = NarrativePlan((B1, B2, late)).validate(canon())
    assert [(x.beat_id, x.code) for x in v] == [("b4", "dead_participant")]


def test_forbidden_and_unknown():
    kill_hero = Beat("bx", "main", ("hero",), effects=(E("hero", "status", "dead"),))
    ghost = Beat("by", "main", ("ghost",))
    codes = {x.code for x in NarrativePlan((kill_hero, ghost)).validate(canon())}
    assert codes == {"forbidden", "unknown_entity"}


def test_precondition_failure():
    v = NarrativePlan((B3,)).validate(canon())
    assert v[0].code == "precondition"


def test_arc_order_and_missing_milestone():
    codes = [x.code for x in NarrativePlan((B2, B1, B3), (ARC,)).validate(canon())]
    assert "arc_order" in codes
    codes = [x.code for x in NarrativePlan((B1, B3), (ARC,)).validate(canon())]
    assert "missing_milestone" in codes


def test_locked_fact():
    g = canon()
    g.lock("sword", "owner")
    assert [x.code for x in NarrativePlan((B1,)).validate(g)] == ["locked_fact"]
    with pytest.raises(CanonError):
        g.lock("sword", "nope")


def test_edit_that_breaks_consequences_is_rejected():
    s = story()
    with pytest.raises(CanonError, match="precondition"):
        s.remove("b1", canon())  # b3 depends on b1's consequence
    with pytest.raises(CanonError, match="dead_participant"):
        s.insert_after("b2", Beat("b25", "main", ("mentor",)), canon())


def test_valid_edits_return_new_plan():
    s = story()
    s2 = s.insert_after("b1", Beat("b15", "side", ("hero",), summary="training"), canon())
    assert [b.beat_id for b in s2.beats] == ["b1", "b15", "b2", "b3"]
    assert [b.beat_id for b in s.beats] == ["b1", "b2", "b3"]
    s3 = s2.replace_beat(Beat("b15", "side", ("hero", "mentor")), canon())
    assert s3.beats_for("mentor") == ["b1", "b15", "b2"]


def test_edit_does_not_blame_preexisting_violations():
    bad = NarrativePlan((B3,))
    bad.insert_after("b3", Beat("ok", "x", ("hero",)), canon())


def test_duplicate_beat_and_entity():
    assert NarrativePlan((B1, B1)).validate(canon())[0].code == "duplicate_beat"
    with pytest.raises(CanonError):
        canon().add_entity("hero", "character")
    with pytest.raises(CanonError):
        canon().relate("hero", "x", "nobody")


def test_canon_from_memory_planes():
    from skeleton.gameforge.batch_b035 import canon_from_memory
    s = PlaneScope("t", "p", "internal")
    m = ProjectMemoryPlanes(s)
    m.write(s, MemoryPlane.DESIGN, "entity:hero", "character", source_id="doc", tick=0)
    m.write(s, MemoryPlane.DESIGN, "fact:hero.home", "village", source_id="doc", tick=0, tags=["canon"])
    g = canon_from_memory(m)
    assert g.entities == {"hero": "character"} and ("hero", "home") in g.locked
    mv = Beat("m", "a", ("hero",), effects=(E("hero", "home", "city"),))
    assert NarrativePlan((mv,)).validate(g)[0].code == "locked_fact"
    m.write(s, MemoryPlane.DESIGN, "fact:ghost.x", "1", source_id="doc", tick=0)
    with pytest.raises(CanonError):
        canon_from_memory(m)


def test_digest_stable():
    assert canon().digest() == canon().digest()
