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


MAX_STREAM_EVENTS = 100000


class StoryAuditAccumulator:
    """Incremental O(characters + distinct facts + event IDs) story audit.

    It never retains scene text, provider responses or an unbounded list of
    bookmarks. Mongo delivers chronological events using the compound index.
    """
    def __init__(self, *, bookmark_limit: int = 100, issue_limit: int = 200):
        if not 1 <= bookmark_limit <= MAX_EVENTS_PER_AUDIT:
            raise ValueError("Invalid audit bookmark limit.")
        self.bookmark_limit = bookmark_limit
        self.issue_limit = issue_limit
        self.branch_id: str | None = None
        self.event_count = 0
        self.issues: list[dict[str, Any]] = []
        self.issue_count = 0
        self.known: dict[str, set[str]] = defaultdict(set)
        self.alive: dict[str, bool] = {}
        self.seen_ids: set[str] = set()
        self.previous_position: tuple[int, int, int] | None = None
        self.last_position: tuple[int, int, int, str] | None = None
        self.bookmarks: list[dict[str, Any]] = []
        self.open_threads: dict[str, str] = {}
        self.interaction_groups: set[str] = set()

    def issue(self, code: str, entry: Mapping[str, Any], detail: str,
              related: str | None = None) -> None:
        self.issue_count += 1
        if len(self.issues) < self.issue_limit:
            self.issues.append(violation(code, entry, detail, related))

    def ingest(self, item: Mapping[str, Any]) -> None:
        branch = str(item.get("branch_id", ""))
        if not branch or (self.branch_id is not None and branch != self.branch_id):
            raise ValueError("Continuity audits must contain exactly one story branch.")
        self.branch_id = branch
        current = position(item)
        if self.last_position is not None and current < self.last_position:
            raise ValueError("Streaming audit requires chronological source ordering.")
        self.last_position = current
        self.event_count += 1
        event_id = str(item["event_id"])
        participants = list(dict.fromkeys(item.get("character_ids") or []))
        witnesses = list(dict.fromkeys(item.get("witness_ids") or []))
        speaker = item.get("speaker_id")
        kind = item.get("kind")
        marker = current[:3]
        if event_id in self.seen_ids:
            self.issue("duplicate_event", item, "Event ID repeats inside the branch.")
        self.seen_ids.add(event_id)
        if marker == self.previous_position:
            self.issue("duplicate_position", item,
                       "Two events share the same act/scene/beat; order is ambiguous.")
        self.previous_position = marker
        if kind not in EVENT_KINDS:
            self.issue("unsupported_kind", item, "Unknown story event kind.")
            return
        if speaker and speaker not in participants:
            self.issue("speaker_missing", item, "Dialogue speaker is not a recorded participant.")
        if kind == "dialogue" and not speaker:
            self.issue("speaker_required", item, "Dialogue requires a named speaker.")
        if not participants and kind in ACTOR_KINDS:
            self.issue("participants_missing", item, "Active event lacks identified characters.")
        if set(witnesses) - set(participants):
            self.issue("witness_missing", item, "Witness must be listed among event participants.")
        for actor in participants:
            self.known.setdefault(actor, set())
        if len(participants) > 1:
            self.interaction_groups.add("|".join(sorted(participants)))
        for actor in participants:
            if self.alive.get(actor) is False and kind in ACTOR_KINDS:
                self.issue("actor_deceased", item,
                           "Character " + actor + " acts after death without revival.")
        if kind == "death":
            for actor in participants:
                if self.alive.get(actor) is False:
                    self.issue("repeated_death", item,
                               "Character " + actor + " is already dead.")
                self.alive[actor] = False
        elif kind == "revival":
            for actor in participants:
                if self.alive.get(actor) is not False:
                    self.issue("revival_without_death", item,
                               "No preceding death is recorded for " + actor + ".")
                self.alive[actor] = True
        else:
            for actor in participants:
                self.alive.setdefault(actor, True)
        if kind in LEARNING_KINDS:
            for actor in participants:
                for fact in item.get("knowledge_required") or []:
                    if fact not in self.known[actor]:
                        self.issue("unearned_knowledge", item,
                                   actor + " refers to unknown fact " + fact + ".")
            for actor in participants:
                self.known[actor].update(item.get("knowledge_granted") or [])
        thread = item.get("thread_key")
        if kind == "promise" and thread:
            if thread in self.open_threads:
                self.issue("duplicate_promise", item,
                           "Thread is already open.", self.open_threads[thread])
            else:
                self.open_threads[thread] = event_id
        if kind == "resolution" and thread:
            if thread not in self.open_threads:
                self.issue("orphan_resolution", item,
                           "Resolution has no earlier open promise.")
            self.open_threads.pop(thread, None)
        self.bookmarks.append({
            "event_id": event_id,
            "key": f"{branch}:a{item['act']}:s{item['scene']}:b{item['beat']}",
            "act": item["act"], "scene": item["scene"], "beat": item["beat"],
            "characters": participants, "witnesses": witnesses,
            "kind": kind, "thread_key": thread,
        })
        if len(self.bookmarks) > self.bookmark_limit:
            del self.bookmarks[0]

    def finish(self, *, complete: bool = True) -> dict[str, Any]:
        # Partial history never receives a clean bill of health, even if its
        # bounded issue list is empty. The limit is a safety budget, not proof.
        return {
            "schema_version": "skeleton.story_continuity.audit.v1",
            "branch_id": self.branch_id,
            "event_count": self.event_count,
            "complete": bool(complete),
            "valid": bool(complete) and self.issue_count == 0,
            "coverage": "full" if complete else "partial",
            "issues": self.issues,
            "issue_count": self.issue_count,
            "open_threads": [
                {"thread_key": key, "introduced_at": event_id}
                for key, event_id in sorted(self.open_threads.items())
            ][:200],
            "bookmarks": self.bookmarks,
            "bookmarks_truncated": self.event_count > self.bookmark_limit,
            "characters": [
                {"id": actor, "alive": self.alive.get(actor),
                 "known_facts": sorted(facts)[:200],
                 "facts_truncated": len(facts) > 200}
                for actor, facts in sorted(self.known.items())
            ][:200],
            "character_index_truncated": len(self.known) > 200,
            "interaction_groups": sorted(self.interaction_groups)[:200],
            "interaction_groups_truncated": len(self.interaction_groups) > 200,
        }


def audit_events(events: Sequence[Mapping[str, Any]], *,
                 complete: bool = True) -> dict[str, Any]:
    """Pure deterministic small-batch validator with full bookmark coverage."""
    if len(events) > MAX_EVENTS_PER_AUDIT:
        raise ValueError("Audit input exceeds bounded event capacity.")
    accumulator = StoryAuditAccumulator(
        bookmark_limit=max(1, len(events)),
    )
    ordered = sorted(events, key=position)
    for item in ordered:
        accumulator.ingest(item)
    # Incomplete history must not create false-positive missing prerequisites:
    # a partial prefix cannot establish what occurred before it.
    report = accumulator.finish(complete=complete)
    if not complete:
        report["issues"] = [x for x in report["issues"] if x["code"] not in
                            {"unearned_knowledge", "orphan_resolution", "revival_without_death"}]
        report["issue_count"] = len(report["issues"])
    return report


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
