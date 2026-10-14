"""Deterministic Dragon Tamagotchi and three idle-only research hatchlings.

This is a reducer, not a scheduler or crawler. Trusted application code must
authenticate owners, authorize acquisitions, check source/rights evidence and
enforce actual idle/resource admission before submitting events. No evidence
here can directly train or promote a model.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import re

LANES = ("article", "video", "updates")
ZERO = "0" * 64
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}\Z")
_TAG = re.compile(r"[a-z0-9][a-z0-9_-]{0,47}\Z")
_HEX = re.compile(r"[0-9a-f]{64}\Z")
MAX_SOURCES = 10000
MAX_EVIDENCE_PER_CHILD = 8192
MIN_IDLE_SECONDS = 300
LEVELS = 20


def _instant(value: str) -> datetime:
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError("bounded timezone-aware timestamp required")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid ISO timestamp") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("timezone-aware timestamp required")
    return result.astimezone(timezone.utc)


def _iso(value: str) -> str:
    return _instant(value).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _id(value: str) -> str:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise ValueError("invalid source or owner identity")
    return value


def _tags(values: tuple[str, ...]) -> tuple[str, ...]:
    if (not isinstance(values, tuple) or len(values) > 64
            or any(not isinstance(t, str) or _TAG.fullmatch(t) is None for t in values)):
        raise ValueError("invalid topic tags")
    return tuple(sorted(set(values)))


def _digest(data: object) -> str:
    return sha256(json.dumps(data, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True, allow_nan=False).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class NestChange:
    sequence: int
    at: str
    action: str
    subject: str
    improvement: str
    previous_digest: str
    state_digest: str
    digest: str


@dataclass(frozen=True)
class Hatchling:
    lane: str
    stage: str = "egg"
    level: int = 0
    # Records unique version receipts, not article text, images or video.
    evidence: tuple[tuple[str, str, str], ...] = ()


@dataclass(frozen=True)
class DragonNest:
    owner: str
    focus_tags: tuple[str, ...]
    adjacent_tags: tuple[str, ...]
    source_ids: tuple[str, ...]
    catalog_digest: str
    consumed: tuple[str, ...] = ()
    consumed_material: tuple[str, ...] = ()
    level: int = 0
    stage: str = "egg"
    children: tuple[Hatchling, ...] = ()
    changes: tuple[NestChange, ...] = ()
    head: str = ZERO


@dataclass(frozen=True)
class AcquiredKnowledge:
    source_id: str
    content_sha256: str
    observed_at: str
    tags: tuple[str, ...]
    reviewed: bool
    lawful: bool
    confidence: float
    # An update candidate must have a dated source revision, not merely
    # be rediscovered from an unchanged search result.
    published_at: str | None = None
    kind: str = "article"


def _state_digest(state: DragonNest) -> str:
    """Commit the entire user-visible reducer state, not only the event prose."""
    return _digest({
        "owner": state.owner,
        "focus_tags": state.focus_tags,
        "adjacent_tags": state.adjacent_tags,
        "source_ids": state.source_ids,
        "catalog_digest": state.catalog_digest,
        "consumed": state.consumed,
        "consumed_material": state.consumed_material,
        "level": state.level,
        "stage": state.stage,
        "children": [
            {"lane": child.lane, "stage": child.stage,
             "level": child.level, "evidence": child.evidence}
            for child in state.children
        ],
    })


def _record(state: DragonNest, *, at: str, action: str,
            subject: str, improvement: str) -> DragonNest:
    timestamp = _iso(at)
    if state.changes and timestamp < state.changes[-1].at:
        raise ValueError("event timestamp cannot move backwards")
    if len(state.changes) >= 40000:
        raise ValueError("nest history capacity exceeded")
    sequence = len(state.changes) + 1
    state_digest = _state_digest(state)
    fields = (state.owner, sequence, timestamp, action, subject, improvement,
              state.head, state_digest)
    digest = _digest(fields)
    entry = NestChange(sequence, timestamp, action, subject, improvement,
                       state.head, state_digest, digest)
    return replace(state, changes=state.changes + (entry,), head=digest)


def new_nest(owner: str, source_ids: tuple[str, ...], *,
             focus_tags: tuple[str, ...], adjacent_tags: tuple[str, ...] = (),
             at: str) -> DragonNest:
    _id(owner)
    if not isinstance(source_ids, tuple) or not 1 <= len(source_ids) <= MAX_SOURCES:
        raise ValueError("nonempty finite source census required")
    for source_id in source_ids:
        _id(source_id)
    if len(set(source_ids)) != len(source_ids):
        raise ValueError("duplicate census identity")
    focus, adjacent = _tags(focus_tags), _tags(adjacent_tags)
    if not focus or set(focus) & set(adjacent):
        raise ValueError("focus required; adjacent categories must be separate")
    sources = tuple(sorted(source_ids))
    state = DragonNest(owner, focus, adjacent, sources,
                       _digest(("dragon-source-census-v1", sources)))
    return _record(state, at=at, action="nest_created", subject=state.catalog_digest,
                   improvement="(baseline: finite source census and three-lane goals recorded)")


def feed_parent(state: DragonNest, source_id: str, *, content_sha256: str,
                at: str, authorized: bool, reviewed: bool, lawful: bool) -> DragonNest:
    if authorized is not True or reviewed is not True or lawful is not True:
        raise PermissionError("parent growth requires authorized reviewed lawful evidence")
    if _id(source_id) not in state.source_ids:
        raise ValueError("source not in committed census")
    if not isinstance(content_sha256, str) or _HEX.fullmatch(content_sha256) is None:
        raise ValueError("content digest required")
    if source_id in state.consumed:
        return state  # retries and republished versions cannot multiply XP
    if content_sha256 in state.consumed_material:
        raise ValueError(
            "duplicate content across census sources cannot earn independent growth"
        )
    consumed = tuple(sorted((*state.consumed, source_id)))
    consumed_material = tuple(sorted((*state.consumed_material, content_sha256)))
    level = min(LEVELS, max(1, math.ceil(LEVELS * len(consumed) / len(state.source_ids))))
    if len(consumed) == len(state.source_ids):
        stage = "adult"
        children = tuple(Hatchling(lane=lane) for lane in LANES)
    elif level < 5:
        stage, children = "hatchling", ()
    elif level < 15:
        stage, children = "juvenile", ()
    else:
        stage, children = "young_adult", ()
    next_state = replace(
        state, consumed=consumed, consumed_material=consumed_material,
        level=level, stage=stage, children=children,
    )
    note = (f"(progress improved: {len(consumed)}/{len(state.source_ids)} reviewed sources; "
            f"level {state.level}->{level}; {state.stage}->{stage})")
    next_state = _record(next_state, at=at, action="parent_grew",
                         subject=_digest((source_id, content_sha256)), improvement=note)
    if children:
        next_state = _record(next_state, at=at, action="three_eggs_laid",
                             subject=state.catalog_digest,
                             improvement="(lineage improved: article, video and updates eggs unlocked)")
    return next_state


def learn_when_idle(state: DragonNest, lane: str, evidence: AcquiredKnowledge, *,
                    at: str, idle_since: str, consented: bool, background_allowed: bool,
                    owner_authorized: bool) -> DragonNest:
    if lane not in LANES or len(state.children) != 3:
        raise ValueError("three hatchlings unlock only after adult source completion")
    if owner_authorized is not True or consented is not True:
        raise PermissionError("idle research requires owner authorization and consent")
    if background_allowed is not True:
        raise PermissionError("foreground or resource-denied work cannot grow hatchlings")
    now, idle = _instant(at), _instant(idle_since)
    if not idle <= now or (now - idle).total_seconds() < MIN_IDLE_SECONDS:
        raise PermissionError("hatchlings can update only after five minutes idle")
    if not isinstance(evidence, AcquiredKnowledge):
        raise ValueError("verified acquisition required")
    _id(evidence.source_id)
    if evidence.kind != lane:
        raise ValueError("source media kind cannot be assigned to a different hatchling")
    if not isinstance(evidence.content_sha256, str) or _HEX.fullmatch(evidence.content_sha256) is None:
        raise ValueError("content identity required")
    if evidence.reviewed is not True or evidence.lawful is not True:
        raise PermissionError("unreviewed or unauthorized source")
    if (type(evidence.confidence) not in (int, float)
            or not math.isfinite(evidence.confidence) or evidence.confidence < 0.8
            or evidence.confidence > 1):
        raise ValueError("low confidence or non-finite evidence")
    tags = _tags(evidence.tags)
    if not set(tags).intersection((*state.focus_tags, *state.adjacent_tags)):
        raise ValueError("irrelevant evidence does not advance a child")
    observed = _instant(evidence.observed_at)
    if observed > now or (now - observed).total_seconds() > 90 * 86400:
        raise ValueError("acquisition observation must be fresh")
    published = _instant(evidence.published_at) if evidence.published_at is not None else None
    if published is not None and published > observed:
        raise ValueError("published date cannot follow observation")
    if lane == "updates" and (published is None or
                              (now - published).total_seconds() > 180 * 86400):
        raise ValueError("update lane requires recent source revision evidence")
    index = LANES.index(lane)
    child = state.children[index]
    receipt = (evidence.source_id, evidence.content_sha256, _iso(evidence.observed_at))
    # Same material does not grow a child just because a URL was revisited.
    for source, digest, observed_at in child.evidence:
        if source == receipt[0] and digest == receipt[1]:
            return state
        if source == receipt[0] and observed_at > receipt[2]:
            raise ValueError("source evidence observation regressed")
    if len(child.evidence) >= MAX_EVIDENCE_PER_CHILD:
        raise ValueError("hatchling evidence budget exceeded")
    updated = child.evidence + (receipt,)
    level = min(LEVELS, 1 + (len(updated) - 1) // 10)
    stage = "hatchling" if level < 5 else "juvenile" if level < 15 else "adult"
    grown = replace(child, evidence=updated, level=level, stage=stage)
    children = state.children[:index] + (grown,) + state.children[index + 1:]
    next_state = replace(state, children=children)
    relevance = "adjacent" if set(tags).isdisjoint(state.focus_tags) else "task"
    note = (f"({lane} improved: new verified {relevance}-relevant information; "
            f"level {child.level}->{level}; {child.stage}->{stage})")
    return _record(next_state, at=at, action="idle_hatchling_grew",
                   subject=_digest((lane, *receipt)), improvement=note)


def verify_change_history(state: DragonNest) -> bool:
    """Checks internal continuity, not external signatures or source truth."""
    previous = ZERO
    for number, entry in enumerate(state.changes, 1):
        if (entry.sequence != number or entry.previous_digest != previous
                or entry.improvement[:1] != "(" or entry.improvement[-1:] != ")"):
            return False
        try:
            if _iso(entry.at) != entry.at:
                return False
        except ValueError:
            return False
        if not isinstance(entry.state_digest, str) or _HEX.fullmatch(entry.state_digest) is None:
            return False
        expected = _digest((state.owner, number, entry.at, entry.action,
                            entry.subject, entry.improvement, previous,
                            entry.state_digest))
        if expected != entry.digest:
            return False
        previous = entry.digest
    return (
        previous == state.head and bool(state.changes)
        and state.changes[-1].state_digest == _state_digest(state)
    )


def nest_snapshot(state: DragonNest) -> dict:
    """Small read-only UI projection. No acquisition or permissions implied."""
    if not verify_change_history(state):
        raise ValueError("nest history verification failed")
    return {
        "schema": "skeleton.dragon.nest.v1",
        "stage": state.stage, "level": state.level,
        "sources_consumed": len(state.consumed),
        "sources_total": len(state.source_ids),
        "children": [
            {"lane": child.lane, "stage": child.stage, "level": child.level,
             "knowledge_items": len(child.evidence)}
            for child in state.children
        ],
        "history_head": state.head,
        "last_changed_at": state.changes[-1].at,
        "last_improvement": state.changes[-1].improvement,
        "promotion_authorized": False,
    }
