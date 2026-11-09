"""Deterministic cross-scene regression cases (no providers, DB or network)."""
from __future__ import annotations

from copy import deepcopy

import pytest

from core.story_continuity import (
    MAX_CONTEXT_CHARS,
    MAX_EVENTS_PER_AUDIT,
    audit_events, event_digest, recall_context,
)


def evt(event_id="e1", *, act=1, scene=1, beat=1, kind="establish",
        actors=("aria",), witnesses=(), speaker=None,
        needs=(), grants=(), thread=None, branch="main", text="Story event"):
    return {
        "event_id": event_id, "branch_id": branch,
        "act": act, "scene": scene, "beat": beat, "kind": kind,
        "character_ids": list(actors), "speaker_id": speaker,
        "witness_ids": list(witnesses), "text": text,
        "knowledge_required": list(needs), "knowledge_granted": list(grants),
        "thread_key": thread, "source_thread_id": "chat-1",
        "source_message_id": "message-" + event_id,
    }


def codes(report):
    return {issue["code"] for issue in report["issues"]}


def test_audit_is_scene_ordered_even_if_records_arrive_out_of_order():
    events = [
        evt("later", act=7, scene=500, kind="dialogue",
            speaker="aria", needs=["door_code"]),
        evt("earlier", act=1, scene=1, kind="discovery", grants=["door_code"]),
    ]
    report = audit_events(events)
    assert report["valid"] is True
    assert report["issues"] == []
    assert report["bookmarks"][0]["event_id"] == "earlier"
    assert report["bookmarks"][1]["key"] == "main:a7:s500:b1"
    assert report["characters"][0]["known_facts"] == ["door_code"]


def test_unearned_knowledge_is_reported_with_act_scene_and_event_provenance():
    report = audit_events([
        evt("first", kind="dialogue", speaker="aria", needs=["secret-king"]),
    ])
    assert report["valid"] is False
    assert codes(report) == {"unearned_knowledge"}
    assert report["issues"][0]["event_id"] == "first"
    assert report["issues"][0]["act"] == 1


def test_actor_death_blocks_later_actions_until_an_explicit_revival():
    report = audit_events([
        evt("death", kind="death"),
        evt("speech", scene=200, kind="dialogue", speaker="aria"),
    ])
    assert "actor_deceased" in codes(report)
    restored = audit_events([
        evt("death", kind="death"),
        evt("revive", scene=12, kind="revival"),
        evt("speech", scene=200, kind="dialogue", speaker="aria"),
    ])
    assert restored["valid"] is True


def test_unexplained_revival_and_repeated_death_are_visible():
    report = audit_events([
        evt("revived", kind="revival"),
        evt("death1", scene=2, kind="death"),
        evt("death2", scene=3, kind="death"),
    ])
    assert codes(report) == {"revival_without_death", "repeated_death"}


def test_interaction_does_not_telepathically_grant_knowledge_to_absent_characters():
    report = audit_events([
        evt("heard", kind="witness", actors=("aria", "ben"),
            witnesses=("ben",), grants=["dragon_key"]),
        evt("outsider", scene=2, kind="dialogue",
            actors=("cleo",), speaker="cleo", needs=["dragon_key"]),
    ])
    assert "unearned_knowledge" in codes(report)
    assert report["interaction_groups"] == ["aria|ben"]


def test_character_who_participates_knows_facts_but_unlisted_speakers_are_errors():
    report = audit_events([
        evt("meeting", actors=("aria", "ben"), kind="interaction",
            grants=["location"]),
        evt("ben", scene=2, actors=("ben",), kind="dialogue",
            speaker="ben", needs=["location"]),
        evt("ghost", scene=3, actors=("aria",),
            kind="dialogue", speaker="cleo"),
    ])
    assert codes(report) == {"speaker_missing"}


def test_open_promise_and_resolution_are_indexed_without_false_completion():
    report = audit_events([
        evt("promised", kind="promise", thread="save_village"),
        evt("talk", scene=2, kind="dialogue", speaker="aria"),
    ])
    assert report["valid"] is True
    assert report["open_threads"] == [
        {"thread_key": "save_village", "introduced_at": "promised"}
    ]
    resolved = audit_events([
        evt("promised", kind="promise", thread="save_village"),
        evt("resolved", scene=1000, kind="resolution",
            thread="save_village"),
    ])
    assert resolved["open_threads"] == []
    assert resolved["valid"] is True


def test_orphan_resolution_and_duplicate_promises_raise_evidence_issues():
    report = audit_events([
        evt("orphan", kind="resolution", thread="unintroduced"),
        evt("p1", scene=2, kind="promise", thread="promise_a"),
        evt("p2", scene=3, kind="promise", thread="promise_a"),
    ])
    assert codes(report) == {"orphan_resolution", "duplicate_promise"}


def test_duplicate_event_identifiers_and_scene_beat_positions_flag_collisions():
    report = audit_events([
        evt("same"),
        evt("same", scene=3),
        evt("different"),
    ])
    assert codes(report) == {"duplicate_event", "duplicate_position"}


def test_branches_are_strictly_isolated_in_audit_and_recall():
    main = evt("main", grants=["code"], kind="discovery")
    alternate = evt("alternate", branch="other", scene=40,
                    needs=["code"], kind="dialogue", speaker="aria")
    with pytest.raises(ValueError, match="one story branch"):
        audit_events([main, alternate])
    result = recall_context([main, alternate], "aria", branch_id="other")
    assert "main" not in result["context"]
    assert "alternate" in result["context"]


def test_incomplete_scan_never_certifies_validity_or_knowledge_preconditions():
    report = audit_events([
        evt("unknown", kind="dialogue", speaker="aria", needs=["before_page"]),
    ], complete=False)
    assert report["complete"] is False
    assert report["valid"] is False
    assert report["issues"] == []
    assert report["coverage"] == "partial"


def test_recall_contains_ordered_bookmarks_source_refs_and_strict_budget():
    events = [
        evt(f"e-{n}", act=1 + n // 100, scene=n,
            text=f"Scene #{n} character decision")
        for n in range(1, 130)
    ]
    recall = recall_context(events, "aria", branch_id="main",
                            limit_chars=500)
    assert recall["truncated"] is True
    assert 0 < recall["included"] < 130
    assert recall["citations"][0]["event_id"] == "e-129"
    assert "[main:A2/S129/B1 id:e-129]" in recall["context"]
    assert len(recall["context"]) <= 500
    with pytest.raises(ValueError):
        recall_context(events, "aria", branch_id="main", limit_chars=MAX_CONTEXT_CHARS + 1)


def test_digest_is_stable_by_semantics_and_does_not_depend_on_mongo_fields():
    event = evt()
    digest = event_digest(event)
    reordered = dict(reversed(list(event.items())))
    reordered["_id"] = "different database identity"
    assert digest == event_digest(reordered)
    changed = deepcopy(event)
    changed["text"] = "A rewritten event"
    assert digest != event_digest(changed)


def test_audit_capacity_and_unknown_kind_fail_closed():
    with pytest.raises(ValueError):
        audit_events([evt(f"n{i}", scene=i + 1) for i in range(MAX_EVENTS_PER_AUDIT + 1)])
    report = audit_events([evt(kind="unknown")])
    assert "unsupported_kind" in codes(report)
    assert report["valid"] is False


def test_empty_full_audit_is_vacuously_consistent_and_partial_never_passes():
    assert audit_events([])["valid"] is True
    assert audit_events([], complete=False)["valid"] is False
