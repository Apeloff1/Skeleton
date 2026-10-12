"""Deterministic, provenance-first story continuity for the Jeeves game builder.

A scene record is evidence of *authored fiction*, not learned model weights.
An event is immutable and branch-scoped; a new branch does not inherit assumed
character knowledge or resurrect dead actors. Audits never silently repair
contradictions and their coverage is explicit so truncated scans cannot pass.

This module is pure and has no database/model/provider side effects.
"""
from __future__ import annotations

from collections import defaultdict
from hashlib import sha256
import json
from typing import Any, Mapping, Sequence

SCHEMA = "skeleton.story_continuity.event.v1"
MAX_EVENTS_PER_AUDIT = 2000
MAX_CONTEXT_CHARS = 12000
EVENT_KINDS = frozenset({
    "establish", "dialogue", "interaction", "witness", "discovery",
    "death", "revival", "promise", "resolution", "departure", "arrival",
})
ACTOR_KINDS = frozenset({"dialogue", "interaction", "witness", "discovery", "promise"})
LEARNING_KINDS = frozenset({"dialogue", "interaction", "witness", "discovery"})


def event_digest(entry: Mapping[str, Any]) -> str:
    """Stable digest for idempotent inserts, independent of Mongo metadata."""
    payload = {
        key: entry[key]
        for key in (
            "event_id", "branch_id", "act", "scene", "beat", "kind",
            "character_ids", "speaker_id", "witness_ids", "text",
            "knowledge_required", "knowledge_granted", "thread_key",
            "source_thread_id", "source_message_id",
        )
    }
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False).encode("utf-8")).hexdigest()


def position(event: Mapping[str, Any]) -> tuple[int, int, int, str]:
    return (int(event["act"]), int(event["scene"]), int(event["beat"]),
            str(event["event_id"]))


def violation(code: str, entry: Mapping[str, Any], detail: str,
              related: str | None = None) -> dict[str, Any]:
    return {
        "code": code,
        "event_id": entry["event_id"],
        "act": entry["act"],
        "scene": entry["scene"],
        "detail": detail,
        "related_event_id": related,
    }


def audit_events(events: Sequence[Mapping[str, Any]], *,
                 complete: bool = True) -> dict[str, Any]:
    """Review a single branch in story order, never in insertion order.

    Only knowledge explicitly witnessed, gained or spoken by a participant
    propagates. Death is a contradiction for later agency without revival.
    An unresolved promise is a warning, not automatically a broken story.
    Missing prerequisites are an error only with a complete prior-history scan.
    """
    if len(events) > MAX_EVENTS_PER_AUDIT:
        raise ValueError("Audit input exceeds bounded event capacity.")
    if not events:
        return {"schema_version": "skeleton.story_continuity.audit.v1",
                "branch_id": None, "event_count": 0, "complete": complete,
                "valid": bool(complete), "issues": [], "open_threads": [],
                "bookmarks": [], "characters": [], "coverage": "full" if complete else "partial"}
    branch_ids = {str(x.get("branch_id", "")) for x in events}
    if len(branch_ids) != 1 or "" in branch_ids:
        raise ValueError("Continuity audits must contain exactly one story branch.")
    ordered = sorted(events, key=position)
    issues: list[dict[str, Any]] = []
    known: dict[str, set[str]] = defaultdict(set)
    alive: dict[str, bool] = {}
    seen: set[str] = set()
    positions: set[tuple[int, int, int]] = set()
    bookmarks: list[dict[str, Any]] = []
    open_threads: dict[str, str] = {}
    pairs: set[str] = set()

    for item in ordered:
        event_id = str(item["event_id"])
        participants = list(dict.fromkeys(item.get("character_ids") or []))
        witnesses = list(dict.fromkeys(item.get("witness_ids") or []))
        speaker = item.get("speaker_id")
        kind = item.get("kind")
        marker = tuple(position(item)[:3])
        if event_id in seen:
            issues.append(violation("duplicate_event", item, "Event ID repeats inside the branch."))
        seen.add(event_id)
        if marker in positions:
            issues.append(violation("duplicate_position", item,
                                    "Two events share the same act/scene/beat; order is ambiguous."))
        positions.add(marker)
        if kind not in EVENT_KINDS:
            issues.append(violation("unsupported_kind", item, "Unknown story event kind."))
            continue
        if speaker and speaker not in participants:
            issues.append(violation("speaker_missing", item,
                                    "Dialogue speaker is not a recorded participant."))
        if kind == "dialogue" and not speaker:
            issues.append(violation("speaker_required", item, "Dialogue requires a named speaker."))
        if not participants and kind in ACTOR_KINDS:
            issues.append(violation("participants_missing", item,
                                    "Active event lacks identified characters."))
        if set(witnesses) - set(participants):
            issues.append(violation("witness_missing", item,
                                    "Witness must be listed among event participants."))
        if len(participants) > 1:
            pairs.add("|".join(sorted(participants)))
        for actor in participants:
            if alive.get(actor) is False and kind in ACTOR_KINDS:
                issues.append(violation("actor_deceased", item,
                                        "Character " + actor + " acts after death without revival."))
        if kind == "death":
            for actor in participants:
                if alive.get(actor) is False:
                    issues.append(violation("repeated_death", item,
                                            "Character " + actor + " is already dead."))
                alive[actor] = False
        elif kind == "revival":
            for actor in participants:
                if alive.get(actor) is not False and complete:
                    issues.append(violation("revival_without_death", item,
                                            "No preceding death is recorded for " + actor + "."))
                alive[actor] = True
        else:
            for actor in participants:
                alive.setdefault(actor, True)
        if kind in LEARNING_KINDS:
            # Required knowledge is checked before granting facts in this event.
            for actor in participants:
                for fact in item.get("knowledge_required") or []:
                    if fact not in known[actor] and complete:
                        issues.append(violation("unearned_knowledge", item,
                                                actor + " refers to unknown fact " + fact + "."))
            # Witnesses and named participants become aware of new facts.
            for actor in participants:
                known[actor].update(item.get("knowledge_granted") or [])
        thread_key = item.get("thread_key")
        if kind == "promise" and thread_key:
            if thread_key in open_threads:
                issues.append(violation("duplicate_promise", item,
                                        "Thread is already open.", open_threads[thread_key]))
            else:
                open_threads[thread_key] = event_id
        if kind == "resolution" and thread_key:
            if thread_key not in open_threads and complete:
                issues.append(violation("orphan_resolution", item,
                                        "Resolution has no earlier open promise."))
            open_threads.pop(thread_key, None)
        bookmarks.append({
            "event_id": event_id,
            "key": f"{item['branch_id']}:a{item['act']}:s{item['scene']}:b{item['beat']}",
            "act": item["act"],
            "scene": item["scene"],
            "beat": item["beat"],
            "characters": participants,
            "witnesses": witnesses,
            "kind": kind,
            "thread_key": thread_key,
        })
    # A truncated scan cannot claim the absence of earlier contradictions.
    return {
        "schema_version": "skeleton.story_continuity.audit.v1",
        "branch_id": ordered[0]["branch_id"],
        "event_count": len(ordered),
        "complete": bool(complete),
        "valid": bool(complete) and not issues,
        "coverage": "full" if complete else "partial",
        "issues": issues[:200],
        "issue_count": len(issues),
        "open_threads": [
            {"thread_key": key, "introduced_at": event_id}
            for key, event_id in sorted(open_threads.items())
        ],
        "bookmarks": bookmarks,
        "characters": [
            {"id": actor, "alive": alive.get(actor), "known_facts": sorted(facts)}
            for actor, facts in sorted(known.items())
        ],
        "interaction_groups": sorted(pairs),
    }


def recall_context(events: Sequence[Mapping[str, Any]], character_id: str, *,
                   branch_id: str, limit_chars: int = MAX_CONTEXT_CHARS,
                   complete: bool = True) -> dict[str, Any]:
    """Bounded, citation-bearing character recall. Never fabricate missing history.

    The caller must report incomplete pagination. Events outside the requested
    branch or without direct character participation are excluded.
    """
    if not 128 <= limit_chars <= MAX_CONTEXT_CHARS:
        raise ValueError("Recall character budget outside supported range.")
    relevant = sorted((
        x for x in events
        if x.get("branch_id") == branch_id and character_id in (x.get("character_ids") or [])
    ), key=position)
    lines = []
    refs = []
    used = 0
    for e in reversed(relevant):
        line = (f"[{e['branch_id']}:A{e['act']}/S{e['scene']}/B{e['beat']} "
                f"id:{e['event_id']}] {e['kind']}: {str(e.get('text') or '').strip()}")
        citation = str(e.get("source_message_id") or e["event_id"])
        line += f" (source:{citation})"
        if used + len(line) + 1 > limit_chars:
            break
        lines.append(line)
        refs.append({"event_id": e["event_id"], "source_message_id": citation})
        used += len(line) + 1
    return {
        "character_id": character_id,
        "branch_id": branch_id,
        "context": "\n".join(lines),
        "citations": refs,
        "included": len(lines),
        "relevant_events": len(relevant),
        "truncated": len(lines) < len(relevant) or not complete,
        "complete_source": bool(complete),
        "instruction_policy": "untrusted_story_evidence_only",
    }
