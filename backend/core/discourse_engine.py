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
from core.databases import lazy_sync_collection

_discourse = lazy_sync_collection(
    "swarm_discourse_logs",
    ([("build_id", 1), ("phase", 1), ("created_at", -1)], {}),
)

_MAX_CONTEXT_FIELD = 256
_MAX_TAGS = 32
_MAX_TAG_LENGTH = 128
_MAX_QUERY_LIMIT = 100


def _validated_context(value: dict) -> dict:
    """Bound only context consumed by selection and persistence."""
    if not isinstance(value, dict):
        raise ValueError("game context must be an object")
    result = {}
    for field in ("genre", "subgenre", "era_id", "engine", "style", "mood"):
        item = value.get(field)
        if item is not None:
            if not isinstance(item, str) or len(item) > _MAX_CONTEXT_FIELD:
                raise ValueError(f"invalid game context field: {field}")
            result[field] = item
    tags = value.get("tags", [])
    if tags is None:
        tags = []
    if (
        not isinstance(tags, (list, tuple))
        or len(tags) > _MAX_TAGS
        or any(not isinstance(tag, str) or len(tag) > _MAX_TAG_LENGTH for tag in tags)
    ):
        raise ValueError("game context tags exceed their size or type budget")
    result["tags"] = list(tags)
    seed = value.get("seed", "")
    if isinstance(seed, bool) or not isinstance(seed, (int, str)) or len(str(seed)) > 128:
        raise ValueError("game context seed is invalid")
    result["seed"] = seed
    era_year = value.get("era_year")
    if era_year is not None:
        if type(era_year) is not int or not -100000 <= era_year <= 100000:
            raise ValueError("game context era_year is invalid")
        result["era_year"] = era_year
    return result


def _bounded_query_limit(value: int) -> int:
    if type(value) is not int or value < 1:
        raise ValueError("discourse query limit must be a positive integer")
    return min(value, _MAX_QUERY_LIMIT)


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
    """Pick a bounded set of agents from validated game context."""
    game_ctx = _validated_context(game_ctx)
    if type(count) is not int or not 1 <= count <= 8:
        raise ValueError("discourse participant count is out of bounds")
    tags: list[str] = []
    for key in ("genre", "subgenre", "era_id", "engine", "style", "mood"):
        v = game_ctx.get(key)
        if isinstance(v, str) and v:
            tags.extend(v.lower().replace("-", "_").split("_"))
    for extra in (game_ctx.get("tags") or []):
        if isinstance(extra, str):
            tags.extend(extra.lower().split())

    # Fencing the token vector bounds work in downstream affinity matching.
    relevant = find_relevant(tags[:64], limit=max(count, 6))
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
    """Compose a bounded lore line even if an archive contains malformed JSON."""
    row = rng.choice(sample) if sample else {}
    if not isinstance(row, dict):
        row = {}
    lore = row.get("lore")
    title = row.get("title")
    if isinstance(lore, list) and lore and isinstance(lore[0], str):
        source = lore[0]
    elif isinstance(title, str):
        source = title
    else:
        source = f"insights on {agent['domain']}"
    # Never split or interpolate full archive-controlled strings. One malformed
    # multi-MiB row must not amplify into every transcript entry.
    first = source[:320].split(".", 1)[0].replace("\r", " ").replace("\n", " ").strip()[:240]
    if not first:
        first = str(agent["domain"])[:240]
    expertise = ", ".join(str(word)[:64] for word in agent["expertise"][:3])
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
    # Guard direct callers and scheduled jobs, not only the HTTP/Pydantic route.
    if not isinstance(build_id, str) or not 1 <= len(build_id.strip()) <= 128:
        raise ValueError("invalid discourse build identifier")
    if not isinstance(phase, str) or not 1 <= len(phase.strip()) <= 64:
        raise ValueError("invalid discourse phase")
    if type(rounds) is not int or not 1 <= rounds <= 10:
        raise ValueError("discourse rounds must be between 1 and 10")
    if type(persist) is not bool:
        raise ValueError("discourse persistence flag must be boolean")
    game_ctx = _validated_context(game_ctx)
    rng = random.Random(f"{build_id}:{phase}:{game_ctx['seed']}")
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
    limit = _bounded_query_limit(limit)
    q: dict[str, Any] = {"build_id": build_id}
    if phase:
        q["phase"] = phase
    out: list[dict] = []
    for d in _discourse.find(q).sort("created_at", -1).limit(limit):
        d.pop("_id", None)
        out.append(d)
    return out


def latest(limit: int = 10) -> list[dict]:
    limit = _bounded_query_limit(limit)
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
