"""
╔════════════════════════════════════════════════════════════════════════╗
║  LEGION DISCOURSE — Layered network of discourse engines               ║
║  ────────────────────────────────────────────────────────────────────  ║
║  Builds a three-layer discourse network, guaranteeing every agent      ║
║  participates meaningfully:                                            ║
║                                                                        ║
║    LAYER 1  Team Discourse                                             ║
║      • Runs inside a single swarm category (e.g. rendering)            ║
║      • 6-10 domain experts + their collection-agent delegates          ║
║      • Outputs: team consensus + open questions                        ║
║                                                                        ║
║    LAYER 2  Legion Discourse                                           ║
║      • Team leaders from each of the 20 swarm categories convene       ║
║      • Joined by strategic collection-agents (one per legion)          ║
║      • Outputs: cross-legion dependencies + risk register              ║
║                                                                        ║
║    LAYER 3  Full Swarm Discourse                                       ║
║      • Every agent (swarm + collection) contributes one aggregated     ║
║        voice (weighted by relevance score)                             ║
║      • Outputs: unified flair + final directives                       ║
║                                                                        ║
║  Each layer feeds its summary/flair forward as "context" to the        ║
║  next, creating a layered network where downstream agents react to     ║
║  upstream consensus.                                                   ║
║                                                                        ║
║  Persistence: `legion_discourse_logs` collection (capped at 5000).     ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations
import os
import random
import time
from typing import Any

from core.swarm_agents import SWARM_DOMAINS, BY_CATEGORY, BY_TEAM, BY_LEGION, find_relevant
from core.collection_agents import (
    build_manifest as coll_manifest,
    find_relevant_collection_agents,
    pick_legion as coll_pick_legion,
    category_histogram as coll_cat_hist,
    total_agents as total_coll_agents,
)
from core.compressed_vault import sample_shard, get_shard_entry
from core import agent_ledger as ledger
from core import whisper_network as whispers
from core.databases import get_sync_db

_db = get_sync_db()
_legion = _db["legion_discourse_logs"]
_legion.create_index([("build_id", 1), ("created_at", -1)])

MOVES_TEAM = ["proposes", "counters", "qualifies", "warns", "extends"]
MOVES_LEGION = ["escalates", "synthesizes", "arbitrates", "mandates", "concedes"]
MOVES_SWARM = ["chants", "affirms", "harmonizes", "crystallizes"]


def _sample_line(agent: dict, rng: random.Random) -> str:
    """Try to pull a real line from the agent's compressed shard, else synthesize."""
    shard_id = agent.get("id")
    if shard_id and get_shard_entry(shard_id):
        try:
            rows = sample_shard(shard_id, k=3)
            if rows:
                row = rng.choice(rows)
                lore = row.get("lore") or []
                if lore:
                    return str(lore[0]).split(".")[0].strip()
                if row.get("title"):
                    return f"doctrine — {row['title']}"
        except Exception:
            pass
    # synthetic fallback
    exp = ", ".join(agent.get("expertise", [])[:2]) or agent.get("domain", "insights")
    return f"observation on {agent.get('domain','the domain')} (keys: {exp})"


def _team_layer(category: str, game_ctx: dict, rng: random.Random, seat_limit: int = 999) -> dict:
    # seat_limit=999 → uncapped: every swarm agent in the category joins, plus
    # every collection-agent delegate we can find for this category.
    swarm_members = BY_CATEGORY.get(category, [])[:seat_limit]
    cat_key = category.replace("_npc", "").replace("qa_security", "qa").split("_")[0]
    delegates = coll_pick_legion(cat_key, limit=seat_limit)

    seats = list(swarm_members) + delegates
    transcript = []
    for seat in seats:
        move = rng.choice(MOVES_TEAM)
        line = _sample_line(seat, rng)
        spec = ledger.pick_specialization(seat, rng)
        sig = seat.get("signature") or seat.get("agent_code", "A????")
        transcript.append({
            "layer": "team",
            "category": category,
            "team_id": seat.get("team_id"),
            "legion_id": seat.get("legion_id"),
            "speaker_id": seat["id"],
            "speaker_code": seat.get("agent_code"),
            "speaker_agent": seat.get("agent", seat.get("id")),
            "source": seat.get("source", "swarm"),
            "move": move,
            "spec": spec,
            "text": f"[{sig}] {move} (spec:{spec}) — \"{line}.\"",
        })

    leader = swarm_members[0] if swarm_members else (delegates[0] if delegates else None)
    if transcript:
        first_lines = [s["text"].split("—")[-1].strip(' ".') for s in transcript[:4]]
        consensus_pick = rng.choice(first_lines or ["n/a"])
        consensus = f"Team {category} ({(leader or {}).get('team_id','T??')}): converged on '{consensus_pick}'."
    else:
        consensus = f"Team {category} had no quorum."
    return {
        "category": category,
        "team_id": (leader or {}).get("team_id"),
        "legion_id": (leader or {}).get("legion_id"),
        "leader": leader,
        "seats": len(seats),
        "consensus": consensus,
        "transcript": transcript,
        "flair": [kw for seat in seats for kw in seat.get("expertise", [])[:2]][:8],
    }


def _legion_layer(team_reports: list[dict], game_ctx: dict, rng: random.Random) -> dict:
    # Full legion council: every single seat from every team's swarm members
    # (not just the team leader) PLUS all strategic collection-agent delegates.
    # This makes every agent heard at the legion tier too.
    council: list[dict] = []
    for t in team_reports:
        for ln in t["transcript"]:
            sid = ln.get("speaker_id")
            if not sid:
                continue
            # Look up full agent dict
            agent = None
            for m in BY_CATEGORY.get(t["category"], []):
                if m["id"] == sid:
                    agent = m
                    break
            if agent is None:
                # try collection-agent
                for c in coll_manifest():
                    if c["id"] == sid:
                        agent = c
                        break
            if agent and agent not in council:
                council.append(agent)

    ctx_tags = []
    for k in ("genre", "subgenre", "era_id", "engine", "mood", "style"):
        v = game_ctx.get(k)
        if isinstance(v, str):
            ctx_tags.extend(v.lower().replace("-", "_").split("_"))
    strategic_delegates = find_relevant_collection_agents(ctx_tags, limit=40)

    transcript = []
    for seat in council + strategic_delegates:
        move = rng.choice(MOVES_LEGION)
        line = _sample_line(seat, rng)
        spec = ledger.pick_specialization(seat, rng)
        sig = seat.get("signature") or seat.get("agent_code", "A????")
        transcript.append({
            "layer": "legion",
            "legion_id": seat.get("legion_id"),
            "team_id": seat.get("team_id"),
            "speaker_id": seat["id"],
            "speaker_code": seat.get("agent_code"),
            "speaker_agent": seat.get("agent", seat.get("id")),
            "move": move,
            "spec": spec,
            "text": f"[Legion · {sig}] {move} (spec:{spec}) — \"{line}.\"",
        })

    risks = [t["consensus"] for t in team_reports[:6]]
    synthesis = " | ".join(risks) if risks else "no teams reported"
    # Per-legion grouped summary (5 legions L1..L5)
    by_legion: dict[str, list[str]] = {}
    for t in team_reports:
        if t.get("legion_id"):
            by_legion.setdefault(t["legion_id"], []).append(t["category"])
    return {
        "seats": len(council) + len(strategic_delegates),
        "council": [
            {"id": c["id"], "code": c.get("agent_code"), "agent": c.get("agent"),
             "team_id": c.get("team_id"), "legion_id": c.get("legion_id")}
            for c in council if c
        ],
        "delegates": [
            {"id": d["id"], "code": d.get("agent_code"), "agent": d.get("agent"),
             "team_id": d.get("team_id"), "legion_id": d.get("legion_id")}
            for d in strategic_delegates
        ],
        "by_legion": {k: v for k, v in by_legion.items()},
        "synthesis": synthesis,
        "transcript": transcript,
    }


def _full_swarm_layer(team_reports: list[dict], legion_report: dict, rng: random.Random, max_voices: int = 1000) -> dict:
    # FULL TOTALITY: include every swarm agent AND every collection agent.
    # max_voices=1000 lets us accommodate the entire 482-agent roster with headroom.
    cat_pools = {c: list(BY_CATEGORY[c]) for c in BY_CATEGORY}
    colls = coll_manifest()
    voices: list[dict] = []
    cats = list(cat_pools.keys())
    # Round-robin across swarm categories first
    while any(cat_pools.values()):
        for cat in cats:
            pool = cat_pools[cat]
            if pool:
                voices.append(pool.pop(0))
            if len(voices) >= max_voices:
                break
        if len(voices) >= max_voices:
            break
    # Then add every collection-agent (one utterance each)
    for c in colls:
        if len(voices) >= max_voices:
            break
        voices.append(c)

    transcript = []
    for v in voices:
        move = rng.choice(MOVES_SWARM)
        line = _sample_line(v, rng)
        spec = ledger.pick_specialization(v, rng)
        sig = v.get("signature") or v.get("agent_code", "A????")
        transcript.append({
            "layer": "full_swarm",
            "team_id": v.get("team_id"),
            "legion_id": v.get("legion_id"),
            "speaker_id": v["id"],
            "speaker_code": v.get("agent_code"),
            "speaker_agent": v.get("agent", v.get("id")),
            "category": v.get("category", "collection"),
            "move": move,
            "spec": spec,
            "text": f"[Swarm · {sig}] {move} (spec:{spec}) — \"{line}.\"",
        })

    # Census stats (every single agent counted, even those not transcripted)
    swarm_census = {"total_swarm_agents": len(SWARM_DOMAINS)}
    coll_census = {"total_collection_agents": total_coll_agents()}
    category_census = {**{c: len(b) for c, b in BY_CATEGORY.items()},
                       **{f"coll:{k}": v for k, v in coll_cat_hist().items()}}

    # Final unified flair pool
    flair_pool = []
    for tr in team_reports:
        flair_pool.extend(tr.get("flair", []))
    final_flair = sorted(set(rng.sample(flair_pool, k=min(8, len(flair_pool))))) if flair_pool else []

    return {
        "voices_sampled": len(voices),
        "census": {**swarm_census, **coll_census, "categories": category_census,
                   "total_agents": swarm_census["total_swarm_agents"] + coll_census["total_collection_agents"]},
        "final_flair": final_flair,
        "chant": f"The Swarm of {swarm_census['total_swarm_agents'] + coll_census['total_collection_agents']} agents affirms the legion's synthesis.",
        "transcript": transcript,
    }


def simulate_network(
    build_id: str,
    phase: str,
    game_ctx: dict,
    *,
    team_categories: list[str] | None = None,
    seat_limit: int = 999,             # uncapped — entire team joins
    max_full_swarm_voices: int = 1000, # fits entire 482-agent roster with headroom
    persist: bool = True,
) -> dict:
    """Run the full three-layer discourse network.

    team_categories: which swarm categories convene teams for this phase.
        Default: all 20 categories → ensures complete swarm participation.
    """
    rng = random.Random(f"{build_id}:{phase}:{game_ctx.get('seed','')}:legion")
    started = time.time()

    categories = team_categories or list(BY_CATEGORY.keys())

    # LAYER 1 — teams (one per category)
    team_reports = [_team_layer(cat, game_ctx, rng, seat_limit=seat_limit) for cat in categories]

    # LAYER 2 — legion council
    legion = _legion_layer(team_reports, game_ctx, rng)

    # LAYER 3 — full swarm chorus
    full = _full_swarm_layer(team_reports, legion, rng, max_voices=max_full_swarm_voices)

    record = {
        "build_id": build_id,
        "phase": phase,
        "created_at": time.time(),
        "elapsed_sec": round(time.time() - started, 3),
        "game_ctx": {k: v for k, v in game_ctx.items() if not isinstance(v, (dict, list))},
        "layers": {
            "team_count": len(team_reports),
            "teams": [
                {
                    "category": t["category"],
                    "team_id": t.get("team_id"),
                    "legion_id": t.get("legion_id"),
                    "leader": (t["leader"] or {}).get("agent") if t["leader"] else None,
                    "leader_code": (t["leader"] or {}).get("agent_code") if t["leader"] else None,
                    "seats": t["seats"],
                    "consensus": t["consensus"],
                    "flair": t["flair"],
                    "transcript_lines": len(t["transcript"]),
                }
                for t in team_reports
            ],
            "legion": {
                "seats": legion["seats"],
                "council": legion["council"],
                "delegates": legion["delegates"],
                "by_legion": legion.get("by_legion", {}),
                "synthesis": legion["synthesis"],
                "transcript_lines": len(legion["transcript"]),
            },
            "full_swarm": {
                "voices_sampled": full["voices_sampled"],
                "census": full["census"],
                "final_flair": full["final_flair"],
                "chant": full["chant"],
                "transcript_lines": len(full["transcript"]),
            },
        },
        "transcript": (
            [ln for t in team_reports for ln in t["transcript"]]
            + legion["transcript"]
            + full["transcript"]
        ),
    }

    # Consolidated agent list for whisper generation
    all_participants: list[dict] = []
    seen_ids: set[str] = set()
    for t in team_reports:
        for ln in t["transcript"]:
            sid = ln.get("speaker_id")
            if sid and sid not in seen_ids:
                # Look up full agent dict from BY_ID (swarm) or coll_manifest
                from core.swarm_agents import BY_ID as _BI
                ag = _BI.get(sid)
                if not ag:
                    ag = next((c for c in coll_manifest() if c["id"] == sid), None)
                if ag:
                    all_participants.append(ag); seen_ids.add(sid)
    # Whispers between participants — FULL swarm side-channel (no artificial cap)
    try:
        wl = whispers.generate_whispers(
            all_participants, record["transcript"],
            build_id=build_id, phase=phase,
            max_whispers=min(500, max(len(all_participants) * 2, 60)),
            persist=persist,
        )
        record["whispers"] = wl
        record["whisper_count"] = len(wl)
    except Exception:
        record["whispers"] = []
        record["whisper_count"] = 0

    # Agent ledger: log every transcript contribution + whispers sent
    try:
        ledger_entries = []
        for ln in record["transcript"]:
            if not ln.get("speaker_code"):
                continue
            ag_stub = {
                "category": ln.get("category") or "general",
                "team_seat": 1 if ln.get("layer") == "legion" else 5,
            }
            ledger_entries.append({
                "agent_code": ln["speaker_code"],
                "speaker_agent": ln.get("speaker_agent"),
                "build_id": build_id,
                "phase": phase,
                "layer": ln.get("layer"),
                "team_id": ln.get("team_id"),
                "legion_id": ln.get("legion_id"),
                "move": ln.get("move"),
                "spec": ln.get("spec"),
                "text": ln.get("text"),
                "influence_score": ledger.influence_score(ag_stub, ln.get("move",""), ln.get("layer","")),
            })
        # Include whisper senders so their ledgers note the side-channel
        for w in record["whispers"]:
            ledger_entries.append({
                "agent_code": w.get("sender_code"),
                "speaker_agent": w.get("sender_agent"),
                "build_id": build_id,
                "phase": phase,
                "layer": "whisper",
                "team_id": w.get("sender_team"),
                "legion_id": w.get("sender_legion"),
                "move": "whispers",
                "spec": w.get("spec"),
                "text": w.get("text"),
                "whispered_to": w.get("recipient_code"),
                "influence_score": 1,
            })
        ledger.log_many(ledger_entries)
        record["ledger_entries_written"] = len(ledger_entries)
    except Exception:
        record["ledger_entries_written"] = 0

    if persist:
        _legion.insert_one(dict(record))
        # keep collection bounded
        total = _legion.count_documents({})
        if total > 2000:
            cursor = _legion.find({}, {"_id": 1}).sort("created_at", 1).limit(total - 2000)
            ids = [d["_id"] for d in cursor]
            if ids:
                _legion.delete_many({"_id": {"$in": ids}})
    record.pop("_id", None)
    return record


def get_for_build(build_id: str, limit: int = 20) -> list[dict]:
    out: list[dict] = []
    for d in _legion.find({"build_id": build_id}).sort("created_at", -1).limit(limit):
        d.pop("_id", None)
        out.append(d)
    return out


def network_stats() -> dict:
    from core.swarm_agents import BY_LEGION as _BL, BY_TEAM as _BT
    return {
        "swarm_agents": len(SWARM_DOMAINS),
        "collection_agents": total_coll_agents(),
        "total_agents": len(SWARM_DOMAINS) + total_coll_agents(),
        "team_categories": len(BY_CATEGORY),
        "swarm_teams": len(_BT),
        "swarm_legions": len(_BL),
        "legion_logs": _legion.count_documents({}),
        "whispers": whispers.stats(),
        "ledger": {"total_entries": ledger._ledger.estimated_document_count()},
    }
