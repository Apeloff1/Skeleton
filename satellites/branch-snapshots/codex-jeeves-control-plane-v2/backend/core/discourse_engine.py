"""
╔════════════════════════════════════════════════════════════════════════╗
║  SWARM DISCOURSE ENGINE                                                ║
║  ────────────────────────────────────────────────────────────────────  ║
║  Simulates multi-turn agent-to-agent discourse during game generation. ║
║                                                                        ║
║  How it works:                                                         ║
║    1. Caller supplies the current build's metadata + phase context.   ║
║    2. Engine picks 5-8 relevant swarm agents (by expertise overlap    ║
║       with the game's genre/era/custom tags).                         ║
║    3. Each selected agent pulls a sample of lore from its compressed  ║
║       micro-DB shard.                                                 ║
║    4. Engine composes a structured discourse log where agents "debate"║
║       tradeoffs, constraints, pitfalls, and solutions specific to     ║
║       the requested game — contributing unique flavor.                ║
║    5. The discourse is persisted in `swarm_discourse_logs` and can    ║
║       be retrieved per-build / per-phase.                             ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations
import os
import random
import time
from typing import Any

from core.swarm_agents import SWARM_DOMAINS, BY_ID, find_relevant, pick_balanced
from core.compressed_vault import sample_shard, get_shard_entry
from core.databases import get_sync_db

_db = get_sync_db()
_discourse = _db["swarm_discourse_logs"]
_discourse.create_index([("build_id", 1), ("phase", 1), ("created_at", -1)])

DISCOURSE_MOVES = [
    "proposes",
    "counters",
    "agrees",
    "qualifies",
    "warns",
    "refines",
    "extends",
    "validates",
    "challenges",
    "concedes",
]


def _gather_agents(game_ctx: dict, count: int = 6) -> list[dict]:
    """Pick 5-8 agents relevant to the game context."""
    tags: list[str] = []
    for key in ("genre", "subgenre", "era_id", "engine", "style", "mood"):
        v = game_ctx.get(key)
        if isinstance(v, str) and v:
            tags.extend(v.lower().replace("-", "_").split("_"))
    for extra in (game_ctx.get("tags") or []):
        if isinstance(extra, str):
            tags.extend(extra.lower().split())

    relevant = find_relevant(tags, limit=max(count, 6))
    if len(relevant) < count:
        # fill with balanced picks
        balance = pick_balanced(count)
        seen = {a["id"] for a in relevant}
        for b in balance:
            if b["id"] not in seen:
                relevant.append(b)
                seen.add(b["id"])
                if len(relevant) >= count:
                    break
    return relevant[:count]


def _agent_line(agent: dict, sample: list[dict], rng: random.Random, move: str) -> str:
    """Compose a single discourse line from one agent, citing its DB."""
    if sample:
        row = rng.choice(sample)
        key_pt = (row.get("lore") or [None])[0] or row.get("title") or agent["domain"]
        # extract first sentence
        if isinstance(key_pt, str):
            first = key_pt.split(".")[0].strip()
        else:
            first = agent["domain"]
    else:
        first = f"insights on {agent['domain']}"
    expertise = ", ".join(agent["expertise"][:3])
    return f"[{agent['agent']} · {agent['category']}] {move} — \"{first}.\" (keys: {expertise})"


def simulate(build_id: str, phase: str, game_ctx: dict, *, rounds: int = 3, persist: bool = True) -> dict:
    """Run a discourse simulation and optionally persist it.

    Returns:
        {
          build_id, phase,
          participants: [...agent summary...],
          transcript: [ { round, speaker_id, speaker_agent, move, text } ],
          summary, unique_flair_tags
        }
    """
    rng = random.Random(f"{build_id}:{phase}:{game_ctx.get('seed','')}")
    agents = _gather_agents(game_ctx, count=6)

    # Sample each agent's DB once (cheap, streams first few rows)
    agent_samples: dict[str, list[dict]] = {}
    for a in agents:
        try:
            agent_samples[a["id"]] = sample_shard(a["id"], k=4) if get_shard_entry(a["id"]) else []
        except Exception:
            agent_samples[a["id"]] = []

    transcript: list[dict] = []
    for r in range(rounds):
        rng.shuffle(agents)
        for a in agents:
            move = rng.choice(DISCOURSE_MOVES)
            line = _agent_line(a, agent_samples.get(a["id"], []), rng, move)
            transcript.append({
                "round": r + 1,
                "speaker_id": a["id"],
                "speaker_agent": a["agent"],
                "domain": a["domain"],
                "category": a["category"],
                "move": move,
                "text": line,
            })

    # Tiny aggregated summary: pick a highlight per category represented
    cats_seen: dict[str, str] = {}
    for entry in transcript:
        cats_seen.setdefault(entry["category"], entry["text"])
    highlight = " · ".join(list(cats_seen.values())[:3])

    # Unique flair tags influence final game output
    flair_pool = []
    for a in agents:
        flair_pool.extend(a["expertise"])
    unique_flair_tags = sorted(set(rng.sample(flair_pool, k=min(6, len(flair_pool)))))

    record = {
        "build_id": build_id,
        "phase": phase,
        "created_at": time.time(),
        "game_ctx": {
            k: game_ctx.get(k)
            for k in ("genre", "subgenre", "era_id", "era_year", "engine", "style", "mood", "seed")
            if k in game_ctx
        },
        "participants": [
            {"id": a["id"], "agent": a["agent"], "domain": a["domain"], "category": a["category"]}
            for a in agents
        ],
        "rounds": rounds,
        "transcript": transcript,
        "highlight": highlight,
        "unique_flair_tags": unique_flair_tags,
    }

    if persist:
        _discourse.insert_one(dict(record))
        # ensure log growth doesn't bloat mongo – cap at 5000 most-recent entries
        total = _discourse.count_documents({})
        if total > 5000:
            # trim oldest
            to_drop = total - 5000
            cursor = _discourse.find({}, {"_id": 1}).sort("created_at", 1).limit(to_drop)
            ids = [d["_id"] for d in cursor]
            if ids:
                _discourse.delete_many({"_id": {"$in": ids}})

    # strip ObjectId from returned record for JSON-safety
    record.pop("_id", None)
    return record


def get_for_build(build_id: str, phase: str | None = None, limit: int = 20) -> list[dict]:
    q: dict[str, Any] = {"build_id": build_id}
    if phase:
        q["phase"] = phase
    out: list[dict] = []
    for d in _discourse.find(q).sort("created_at", -1).limit(limit):
        d.pop("_id", None)
        out.append(d)
    return out


def latest(limit: int = 10) -> list[dict]:
    out: list[dict] = []
    for d in _discourse.find({}).sort("created_at", -1).limit(limit):
        d.pop("_id", None)
        out.append(d)
    return out


def discourse_stats() -> dict:
    return {
        "total_logs": _discourse.count_documents({}),
        "total_domains": len(SWARM_DOMAINS),
    }
