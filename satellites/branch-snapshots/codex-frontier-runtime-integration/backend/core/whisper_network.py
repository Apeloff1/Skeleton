"""
╔════════════════════════════════════════════════════════════════════════╗
║  WHISPER NETWORK — private agent-to-agent side-channel                 ║
║                                                                        ║
║  Between rounds, agents can whisper a short hint to another agent      ║
║  whose expertise overlaps theirs. Whispers are persisted in Mongo      ║
║  collection `agent_whispers` and can be retrieved per-build or         ║
║  per-recipient, giving a secondary discourse layer you can inspect.    ║
║                                                                        ║
║  Public API:                                                           ║
║     • generate_whispers(participants, transcript, build_id, phase, n)  ║
║     • recent(recipient_code, limit)                                    ║
║     • for_build(build_id, limit)                                       ║
║     • stats()                                                          ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations
import os
import random
import time

from core.databases import get_sync_db

_db = get_sync_db()
_whispers = _db["agent_whispers"]
_whispers.create_index([("build_id", 1), ("created_at", -1)])
_whispers.create_index([("recipient_code", 1), ("created_at", -1)])

WHISPER_CAP = int(os.environ.get("WHISPER_CAP", "15000"))

_WHISPER_TEMPLATES = [
    "{sender_code}→{recipient_code}: brace for a {spec} spike on '{topic}'",
    "{sender_code}→{recipient_code}: align your {spec} with my last move on '{topic}'",
    "{sender_code}→{recipient_code}: I see a risk in '{topic}' — route it through {spec}",
    "{sender_code}→{recipient_code}: piggyback my verdict; mirror {spec} for '{topic}'",
    "{sender_code}→{recipient_code}: escalate to legion if '{topic}' drifts from {spec}",
    "{sender_code}→{recipient_code}: warn the full swarm — '{topic}' depends on {spec} stability",
    "{sender_code}→{recipient_code}: caucus with me next round on '{topic}' via {spec}",
    "{sender_code}→{recipient_code}: reclaim budget from '{topic}' into {spec} — faster path",
]


def _overlap(a: dict, b: dict) -> int:
    ae = set(e.lower() for e in (a.get("expertise") or []))
    be = set(e.lower() for e in (b.get("expertise") or []))
    score = len(ae & be)
    # bonus if same legion / team
    if a.get("legion_id") and a.get("legion_id") == b.get("legion_id"):
        score += 2
    if a.get("team_id") and a.get("team_id") == b.get("team_id"):
        score += 1
    return score


def generate_whispers(
    participants: list[dict],
    transcript: list[dict],
    build_id: str,
    phase: str,
    max_whispers: int = 30,
    persist: bool = True,
) -> list[dict]:
    """Create `max_whispers` private whispers between participants.

    Each whisper is tied to the most recent transcript line of the sender
    and targets a recipient with the highest expertise overlap.
    """
    if not participants:
        return []
    rng = random.Random(f"{build_id}:{phase}:whispers")
    whispers: list[dict] = []

    # Build "most recent utterance" map keyed by speaker_code → text+topic
    by_speaker: dict[str, dict] = {}
    for ln in transcript:
        code = ln.get("speaker_id") or ln.get("speaker_code")
        if not code:
            continue
        by_speaker[code] = ln

    for _ in range(max_whispers):
        sender = rng.choice(participants)
        # pick a recipient that's NOT the sender with best overlap
        pool = [p for p in participants if p.get("id") != sender.get("id")]
        if not pool:
            continue
        pool.sort(key=lambda r: -_overlap(sender, r))
        candidate_set = pool[:6] or pool
        recipient = rng.choice(candidate_set)

        sender_code = sender.get("agent_code") or sender.get("id", "A????")
        recipient_code = recipient.get("agent_code") or recipient.get("id", "A????")
        spec = rng.choice(sender.get("expertise") or ["general-practice"])

        last = by_speaker.get(sender.get("id")) or {}
        topic = (last.get("text") or last.get("move") or sender.get("domain") or "the phase")
        # Keep topic short
        topic_short = str(topic).split("—")[-1].strip(' ".')[:60] or "the phase"

        tpl = rng.choice(_WHISPER_TEMPLATES)
        text = tpl.format(sender_code=sender_code, recipient_code=recipient_code, spec=spec, topic=topic_short)

        w = {
            "build_id": build_id,
            "phase": phase,
            "created_at": time.time(),
            "sender_id": sender.get("id"),
            "sender_code": sender_code,
            "sender_agent": sender.get("agent"),
            "sender_team": sender.get("team_id"),
            "sender_legion": sender.get("legion_id"),
            "recipient_id": recipient.get("id"),
            "recipient_code": recipient_code,
            "recipient_agent": recipient.get("agent"),
            "recipient_team": recipient.get("team_id"),
            "recipient_legion": recipient.get("legion_id"),
            "topic": topic_short,
            "spec": spec,
            "text": text,
        }
        whispers.append(w)

    if persist and whispers:
        try:
            _whispers.insert_many([dict(w) for w in whispers], ordered=False)
            # cap
            total = _whispers.estimated_document_count()
            if total > WHISPER_CAP + 500:
                overflow = total - WHISPER_CAP
                cursor = _whispers.find({}, {"_id": 1}).sort("created_at", 1).limit(overflow)
                ids = [d["_id"] for d in cursor]
                if ids:
                    _whispers.delete_many({"_id": {"$in": ids}})
        except Exception:
            pass
    return whispers


def recent(recipient_code: str, limit: int = 20) -> list[dict]:
    out = []
    for d in _whispers.find({"recipient_code": recipient_code}).sort("created_at", -1).limit(limit):
        d.pop("_id", None)
        out.append(d)
    return out


def for_build(build_id: str, limit: int = 200) -> list[dict]:
    out = []
    for d in _whispers.find({"build_id": build_id}).sort("created_at", -1).limit(limit):
        d.pop("_id", None)
        out.append(d)
    return out


def stats() -> dict:
    return {
        "total_whispers": _whispers.estimated_document_count(),
        "cap": WHISPER_CAP,
    }
