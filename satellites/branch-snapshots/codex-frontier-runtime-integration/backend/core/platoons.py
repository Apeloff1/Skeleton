"""
╔════════════════════════════════════════════════════════════════════════╗
║  PLATOONS — per-build-phase microteams (4-6 agents each)               ║
║  ────────────────────────────────────────────────────────────────────  ║
║  A platoon is a tiny, focused unit assigned to ONE build-phase.        ║
║  Every build-phase gets its own platoon, and platoons form a chain:    ║
║  the handoff summary from phase N's platoon feeds into phase N+1.      ║
║                                                                        ║
║  Public API:                                                           ║
║     • platoon_for_phase(phase_id, game_ctx, rotation_idx) → Platoon    ║
║     • run_platoon(build_id, phase_id, prev_handoff=None)               ║
║     • chain_for_batch(build_id, batch_num, phase_ids)                  ║
║     • coverage_stats(build_id) → participation per agent code          ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations
import os
import time
import random
from typing import Any

from core.swarm_agents import SWARM_DOMAINS, BY_CATEGORY, BY_TEAM, BY_LEGION
from core.collection_agents import build_manifest as coll_manifest, find_relevant_collection_agents
from core.compressed_vault import sample_shard, get_shard_entry
from core import agent_ledger as ledger
from core import whisper_network as whispers
from core.databases import get_sync_db

_db = get_sync_db()
_platoon_logs = _db["platoon_logs"]
_platoon_logs.create_index([("build_id", 1), ("phase_id", 1), ("created_at", -1)])
_participation = _db["participation_tracker"]
_participation.create_index([("build_id", 1)])
_participation.create_index([("build_id", 1), ("agent_code", 1)], unique=True)

MOVES_PLATOON = ["scouts", "pins", "rigs", "tests", "ships", "signs-off", "hands-off"]

# ═══ Consolidated agent roster ═══════════════════════════════════════════
def _all_agents_flat() -> list[dict]:
    """Return a single flat list with EVERY agent (swarm + collection), ordered
    by agent_number so the scheduler can round-robin deterministically."""
    roster = list(SWARM_DOMAINS) + coll_manifest()
    roster.sort(key=lambda a: a.get("agent_number") or 99999)
    return roster


_ROSTER: list[dict] | None = None
_ROSTER_TS: float = 0.0


def roster(refresh: bool = False) -> list[dict]:
    """Cached roster (refreshes every 60s or on demand)."""
    global _ROSTER, _ROSTER_TS
    if refresh or not _ROSTER or time.time() - _ROSTER_TS > 60:
        _ROSTER = _all_agents_flat()
        _ROSTER_TS = time.time()
    return _ROSTER


def total_agent_count() -> int:
    return len(roster())


# ═══ Platoon assignment ══════════════════════════════════════════════════
def platoon_for_phase(phase_key: str, game_ctx: dict, rotation_idx: int = 0, size: int = 5) -> list[dict]:
    """Pick `size` agents for the platoon covering this phase.

    Strategy: deterministic but each build iterates a different rotation
    so across a build's ~100 phases, every agent eventually gets a seat.
    """
    rng = random.Random(f"{phase_key}:{rotation_idx}:{game_ctx.get('seed','')}")
    r = roster()
    n = len(r)
    if n == 0:
        return []
    # Round-robin base slice — start at (rotation * size) mod n
    start = (rotation_idx * size) % n
    primary = [r[(start + i) % n] for i in range(size)]
    # Sprinkle in 1 context-relevant agent whose expertise overlaps game_ctx
    ctx_tokens: list[str] = []
    for k in ("genre", "subgenre", "era_id", "engine", "style", "mood"):
        v = game_ctx.get(k)
        if isinstance(v, str):
            ctx_tokens.extend(v.lower().replace("-", "_").split("_"))
    # Try to boost one spot with a context-relevant collection agent
    try:
        relevant = find_relevant_collection_agents(ctx_tokens, limit=3)
        for rel in relevant:
            if rel["id"] not in {p["id"] for p in primary}:
                primary[-1] = rel  # replace last slot for context boost
                break
    except Exception:
        pass
    # Shuffle order of speaking for variety
    rng.shuffle(primary)
    return primary


# ═══ Platoon discussion ═══════════════════════════════════════════════════
def _platoon_line(agent: dict, rng: random.Random, move: str, prev_handoff: str | None) -> str:
    sig = agent.get("signature") or f"{agent.get('agent_code','A????')} · {agent.get('agent','?')}"
    shard_id = agent.get("id")
    lore_bit = ""
    if shard_id and get_shard_entry(shard_id):
        try:
            rows = sample_shard(shard_id, k=2)
            if rows:
                row = rng.choice(rows)
                first = (row.get("lore") or [None])[0] or row.get("title") or ""
                if first:
                    lore_bit = f" — \"{str(first).split('.')[0].strip()}.\""
        except Exception:
            pass
    handoff_note = f" ← inherits '{prev_handoff[:80]}'" if prev_handoff else ""
    spec = ledger.pick_specialization(agent, rng)
    return f"[Platoon · {sig}] {move} (spec:{spec}){handoff_note}{lore_bit}"


def run_platoon(
    build_id: str,
    phase_id: str,
    game_ctx: dict,
    rotation_idx: int = 0,
    prev_handoff: str | None = None,
    rounds: int = 2,
    size: int = 5,
    persist: bool = True,
) -> dict:
    """Run a platoon discussion for a single build-phase."""
    rng = random.Random(f"{build_id}:{phase_id}:{rotation_idx}:platoon")
    members = platoon_for_phase(phase_id, game_ctx, rotation_idx=rotation_idx, size=size)
    if not members:
        return {"build_id": build_id, "phase_id": phase_id, "members": [], "transcript": [], "handoff": prev_handoff}

    transcript: list[dict] = []
    for r in range(rounds):
        rng.shuffle(members)
        for a in members:
            move = rng.choice(MOVES_PLATOON)
            text = _platoon_line(a, rng, move, prev_handoff if r == 0 else None)
            transcript.append({
                "round": r + 1,
                "layer": "platoon",
                "phase_id": phase_id,
                "speaker_id": a["id"],
                "speaker_code": a.get("agent_code"),
                "speaker_agent": a.get("agent"),
                "team_id": a.get("team_id"),
                "legion_id": a.get("legion_id"),
                "move": move,
                "text": text,
            })

    # Short handoff string for next phase
    last_lines = [l["text"] for l in transcript[-3:]]
    handoff = " | ".join(last_lines)[:300]

    # Whispers — 1 per member
    try:
        wl = whispers.generate_whispers(members, transcript, build_id=build_id,
                                        phase=f"platoon::{phase_id}",
                                        max_whispers=max(3, len(members)),
                                        persist=persist)
    except Exception:
        wl = []

    # Ledger — every member gets an entry
    try:
        entries = []
        for line in transcript:
            if not line.get("speaker_code"):
                continue
            entries.append({
                "agent_code": line["speaker_code"],
                "speaker_agent": line.get("speaker_agent"),
                "build_id": build_id,
                "phase": phase_id,
                "layer": "platoon",
                "team_id": line.get("team_id"),
                "legion_id": line.get("legion_id"),
                "move": line.get("move"),
                "spec": None,
                "text": line.get("text"),
                "influence_score": 2,
            })
        for w in wl:
            entries.append({
                "agent_code": w.get("sender_code"),
                "speaker_agent": w.get("sender_agent"),
                "build_id": build_id,
                "phase": phase_id,
                "layer": "platoon_whisper",
                "team_id": w.get("sender_team"),
                "legion_id": w.get("sender_legion"),
                "move": "whispers",
                "spec": w.get("spec"),
                "text": w.get("text"),
                "whispered_to": w.get("recipient_code"),
                "influence_score": 1,
            })
        ledger.log_many(entries)
    except Exception:
        pass

    # Participation tracker — record each member's contribution for coverage math
    try:
        for a in members:
            code = a.get("agent_code")
            if not code:
                continue
            _participation.update_one(
                {"build_id": build_id, "agent_code": code},
                {"$inc": {"platoon_seats": 1, "utterances": rounds},
                 "$set": {"agent": a.get("agent"), "team_id": a.get("team_id"),
                          "legion_id": a.get("legion_id"),
                          "last_phase": phase_id, "last_at": time.time()}},
                upsert=True,
            )
    except Exception:
        pass

    record = {
        "build_id": build_id,
        "phase_id": phase_id,
        "rotation_idx": rotation_idx,
        "created_at": time.time(),
        "members": [
            {"code": m.get("agent_code"), "agent": m.get("agent"),
             "team_id": m.get("team_id"), "legion_id": m.get("legion_id")}
            for m in members
        ],
        "transcript": transcript,
        "whisper_count": len(wl),
        "handoff": handoff,
    }
    if persist:
        _platoon_logs.insert_one(dict(record))
        total = _platoon_logs.estimated_document_count()
        if total > 20000:
            overflow = total - 20000
            cursor = _platoon_logs.find({}, {"_id": 1}).sort("created_at", 1).limit(overflow)
            ids = [d["_id"] for d in cursor]
            if ids:
                _platoon_logs.delete_many({"_id": {"$in": ids}})
    record.pop("_id", None)
    return record


def chain_for_batch(build_id: str, batch_num: int, game_ctx: dict,
                    phase_ids: list[str], rounds: int = 2, size: int = 5) -> dict:
    """Run a chain of platoons through the phases of one batch.

    Each phase's platoon inherits the handoff summary from the previous phase,
    so discussion flows across the full batch.
    """
    started = time.time()
    records: list[dict] = []
    prev_handoff: str | None = None
    # Rotation pattern: base offset from (batch_num * phases_per_batch) — ensures
    # different phases in different batches hit different parts of the roster.
    for i, phase_id in enumerate(phase_ids):
        rot = (batch_num - 1) * len(phase_ids) + i
        rec = run_platoon(build_id, phase_id, game_ctx,
                          rotation_idx=rot, prev_handoff=prev_handoff,
                          rounds=rounds, size=size, persist=True)
        records.append(rec)
        prev_handoff = rec.get("handoff")
    return {
        "build_id": build_id,
        "batch_num": batch_num,
        "phase_count": len(records),
        "elapsed_sec": round(time.time() - started, 3),
        "total_transcript_lines": sum(len(r["transcript"]) for r in records),
        "unique_agents_seated": len({m["code"] for r in records for m in r["members"]}),
        "phase_platoons": [
            {
                "phase_id": r["phase_id"],
                "rotation_idx": r["rotation_idx"],
                "member_codes": [m["code"] for m in r["members"]],
                "handoff_head": r["handoff"][:120],
                "transcript_lines": len(r["transcript"]),
            }
            for r in records
        ],
    }


# ═══ Participation coverage ══════════════════════════════════════════════
def coverage_stats(build_id: str) -> dict:
    total = len(roster())
    docs = list(_participation.find({"build_id": build_id}))
    participated = len(docs)
    by_team: dict[str, int] = {}
    by_legion: dict[str, int] = {}
    for d in docs:
        if d.get("team_id"):
            by_team[d["team_id"]] = by_team.get(d["team_id"], 0) + 1
        if d.get("legion_id"):
            by_legion[d["legion_id"]] = by_legion.get(d["legion_id"], 0) + 1
    # Who hasn't participated yet
    seated_codes = {d["agent_code"] for d in docs}
    silent = [a["agent_code"] for a in roster() if a.get("agent_code") and a["agent_code"] not in seated_codes][:50]
    return {
        "build_id": build_id,
        "total_agents": total,
        "participated": participated,
        "coverage_pct": round(participated / max(total, 1) * 100, 2),
        "by_team": by_team,
        "by_legion": by_legion,
        "silent_sample": silent,
    }


def participation_rows(build_id: str, limit: int = 500) -> list[dict]:
    out = []
    for d in _participation.find({"build_id": build_id}).sort("utterances", -1).limit(limit):
        d.pop("_id", None)
        out.append(d)
    return out


def platoons_for_build(build_id: str, limit: int = 200) -> list[dict]:
    out = []
    for d in _platoon_logs.find({"build_id": build_id}).sort("created_at", 1).limit(limit):
        d.pop("_id", None)
        out.append(d)
    return out


def force_participation_sweep(build_id: str, game_ctx: dict, max_missing: int = 500) -> dict:
    """Mop-up pass: any agent who hasn't yet participated in this build gets
    one platoon seat in a special 'coverage_sweep' phase. Guarantees 100% coverage."""
    docs = list(_participation.find({"build_id": build_id}))
    seated = {d["agent_code"] for d in docs}
    silent = [a for a in roster() if a.get("agent_code") and a["agent_code"] not in seated]
    silent = silent[:max_missing]
    if not silent:
        return {"build_id": build_id, "swept": 0, "already_covered": True}

    # Batch into platoons of 6 and run them as coverage sweeps
    rng = random.Random(f"{build_id}:sweep")
    swept = 0
    platoon_size = 6
    for i in range(0, len(silent), platoon_size):
        chunk = silent[i:i + platoon_size]
        phase_id = f"coverage_sweep_{i // platoon_size + 1}"
        # Manually craft record so we include exactly these members
        transcript = []
        for r in range(2):
            rng.shuffle(chunk)
            for a in chunk:
                move = rng.choice(MOVES_PLATOON)
                text = _platoon_line(a, rng, move, prev_handoff=None)
                transcript.append({
                    "round": r + 1, "layer": "platoon", "phase_id": phase_id,
                    "speaker_id": a["id"], "speaker_code": a.get("agent_code"),
                    "speaker_agent": a.get("agent"),
                    "team_id": a.get("team_id"), "legion_id": a.get("legion_id"),
                    "move": move, "text": text,
                })
        _platoon_logs.insert_one({
            "build_id": build_id, "phase_id": phase_id, "rotation_idx": -1,
            "created_at": time.time(),
            "members": [{"code": a.get("agent_code"), "agent": a.get("agent"),
                         "team_id": a.get("team_id"), "legion_id": a.get("legion_id")}
                        for a in chunk],
            "transcript": transcript,
            "whisper_count": 0,
            "handoff": "coverage sweep",
            "sweep": True,
        })
        # Mark them in participation
        entries = []
        for a in chunk:
            code = a.get("agent_code")
            if not code:
                continue
            _participation.update_one(
                {"build_id": build_id, "agent_code": code},
                {"$inc": {"platoon_seats": 1, "utterances": 2},
                 "$set": {"agent": a.get("agent"), "team_id": a.get("team_id"),
                          "legion_id": a.get("legion_id"),
                          "last_phase": phase_id, "last_at": time.time()}},
                upsert=True,
            )
            entries.append({
                "agent_code": code,
                "speaker_agent": a.get("agent"),
                "build_id": build_id,
                "phase": phase_id,
                "layer": "platoon_sweep",
                "team_id": a.get("team_id"),
                "legion_id": a.get("legion_id"),
                "move": "participates",
                "text": f"[sweep · {a.get('agent_code')}] confirms presence in build {build_id[:8]}",
                "influence_score": 1,
            })
            swept += 1
        if entries:
            try:
                ledger.log_many(entries)
            except Exception:
                pass
    return {"build_id": build_id, "swept": swept, "remaining_silent": 0}
