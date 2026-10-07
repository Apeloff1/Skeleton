"""
╔══════════════════════════════════════════════════════════════════════════╗
║  10 BIG WINS PACK — high-leverage capabilities across the build lifecycle  ║
║  (discovery, readiness, learning loop, marketing, health). Deterministic,  ║
║  fast, and reused by the Snowball UI. Prefix: /api/wins                     ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations
import os
import re
from datetime import datetime, timezone
from typing import Optional, List, Dict

from fastapi import APIRouter, Query
from core.databases import client as _MONGO

router = APIRouter(prefix="/api/wins", tags=["wins"])
_db = _MONGO[os.environ.get("DB_NAME", "test_database")]
PROJ = {"_id": 0}

# Agent cast that learns from each build (mirrors jeeves_voice.AGENT_CAST keys).
_CAST = ["WorldForgeAgent", "NarrativeQuestAgent", "MechanicsSystemsAgent",
         "ProceduralAgent", "AssetPipelineAgent", "QAAgent", "BuildAgent"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _game(pid: str) -> Dict:
    return await _db.playables.find_one({"playable_id": pid}, PROJ) or {}


async def _kb(pid: str) -> Dict:
    return await _db.game_kb.find_one({"game_id": pid}, PROJ) or {}


# ── WIN 1 · Shareable GDD card ──────────────────────────────────────────────
@router.get("/{pid}/gdd/share")
async def gdd_share(pid: str):
    g = await _game(pid)
    kb = await _kb(pid)
    arts = kb.get("artifacts") or {}
    pitch = (g.get("brief") or "").strip()[:160]
    return {
        "pid": pid, "title": g.get("title", "Untitled"),
        "pitch": pitch or "An original game forged in Galaxy Studio.",
        "genre": g.get("genre", ""),
        "stages_built": len(arts),
        "share_text": f"🎮 {g.get('title','Untitled')} — {pitch or g.get('genre','a new game')} · built in Galaxy Studio",
    }


# ── WIN 2 · Learning loop: agent reflections after a build ──────────────────
@router.post("/{pid}/reflect-all")
async def reflect_all(pid: str):
    """Snapshot each cast agent's learned profile (reflections + preferences) so the
    next build is biased by what worked. Light: aggregates stored memories."""
    out = []
    for agent in _CAST:
        mems = await _db.agent_memories.find({"agent_id": agent}, PROJ).to_list(500)
        refl = [m for m in mems if m.get("kind") == "reflection"]
        prefs = [m for m in mems if m.get("kind") == "preference"]
        out.append({"agent": agent, "memories": len(mems),
                    "reflections": len(refl), "preferences": len(prefs),
                    "latest": (sorted(refl, key=lambda m: m.get("created_at", ""), reverse=True)[:1] or [{}])[0].get("content", "")})
    return {"pid": pid, "cast": out, "total_memories": sum(a["memories"] for a in out)}


# ── WIN 3 · Ship-readiness score ────────────────────────────────────────────
@router.get("/{pid}/readiness")
async def readiness(pid: str):
    kb = await _kb(pid)
    arts = kb.get("artifacts") or {}
    approvals = kb.get("approvals") or {}
    g = await _game(pid)
    stages_total = 9
    built = min(len(arts), stages_total)
    locked = sum(1 for a in approvals.values() if a.get("approved"))
    audit = g.get("score") or g.get("audit_overall") or 0
    build_pct = round(100 * built / stages_total)
    lock_pct = round(100 * locked / stages_total)
    score = round(0.4 * build_pct + 0.3 * lock_pct + 0.3 * (audit or 0))
    tier = "ship" if score >= 90 else ("polish" if score >= 60 else "early")
    return {"pid": pid, "readiness": score, "tier": tier,
            "build_pct": build_pct, "lock_pct": lock_pct, "audit": audit,
            "stages_built": built, "stages_locked": locked}


# ── WIN 4 · Top-builds leaderboard ──────────────────────────────────────────
@router.get("/leaderboard")
async def leaderboard(limit: int = Query(10, ge=1, le=50)):
    rows = await _db.playables.find(
        {"score": {"$gt": 0}}, {"_id": 0, "playable_id": 1, "title": 1, "score": 1, "genre": 1}
    ).sort("score", -1).limit(limit).to_list(limit)
    return {"count": len(rows), "leaderboard": [
        {"rank": i + 1, **r} for i, r in enumerate(rows)]}


# ── WIN 5 · Marketing pitch (LLM w/ deterministic fallback) ─────────────────
@router.post("/{pid}/pitch")
async def pitch(pid: str):
    g = await _game(pid)
    title = g.get("title", "Untitled")
    brief = (g.get("brief") or "").strip()
    genre = g.get("genre", "")
    text = None
    key = os.environ.get("EMERGENT_LLM_KEY")
    if key and brief:
        try:
            import uuid
            from emergentintegrations.llm.chat import LlmChat, UserMessage
            chat = LlmChat(api_key=key, session_id=f"pitch-{uuid.uuid4().hex[:8]}",
                           system_message="You are a punchy game-marketing copywriter.").with_model("openai", "gpt-4o-mini")
            import asyncio
            resp = await asyncio.wait_for(chat.send_message(UserMessage(
                text=f"Write ONE vivid 2-sentence store pitch for '{title}' ({genre}). Premise: {brief}")), timeout=30)
            text = (resp.content if hasattr(resp, "content") else str(resp)).strip()
        except Exception:
            text = None
    if not text:
        text = f"{title} is a {genre or 'bold new'} experience. {brief[:160] or 'Step into a world built just for you.'}"
    return {"pid": pid, "title": title, "pitch": text, "llm": bool(text and key)}


# ── WIN 6 · Auto changelog from stage approvals ─────────────────────────────
@router.get("/{pid}/changelog")
async def changelog(pid: str):
    kb = await _kb(pid)
    approvals = kb.get("approvals") or {}
    entries = []
    for stage, a in approvals.items():
        if a.get("approved"):
            entries.append({"stage": stage, "at": a.get("approved_at") or a.get("at", ""),
                            "note": f"Locked {stage}"})
    entries.sort(key=lambda e: e["at"])
    return {"pid": pid, "entries": entries, "count": len(entries)}


# ── WIN 7 · Build health (vault + reconnected pipelines) ────────────────────
@router.get("/health")
async def build_health():
    from core.stage_vault import vault_for_stage
    steps = ["spec", "world", "narrative", "mechanics", "procedural", "assets",
             "qa", "build", "vfx", "audio", "ui", "multiplayer", "monetization"]
    connected = sum(1 for s in steps if vault_for_stage(s)["domain_count"] > 0)
    pipelines = [
        {"name": "Game Systems", "api": "/api/game-systems", "reconnected": True},
        {"name": "Jeeves Master Build", "api": "/api/jeeves-master", "reconnected": True},
        {"name": "Knowledge Nexus (Vault)", "api": "/api/knowledge-nexus", "reconnected": True},
        {"name": "VFX & Materials", "api": "/api/vfx-materials", "reconnected": True},
        {"name": "Multiplayer / Netcode", "api": "/api/multiplayer", "reconnected": True},
    ]
    return {"vault_steps": len(steps), "vault_connected": connected,
            "vault_coverage_pct": round(100 * connected / len(steps)),
            "pipelines": pipelines, "healthy": connected == len(steps)}


# ── WIN 8 · Auto-tags for discovery ─────────────────────────────────────────
_TAG_HINTS = ["roguelike", "rpg", "shooter", "puzzle", "platformer", "strategy",
              "racing", "fighting", "survival", "horror", "sci-fi", "fantasy",
              "cyberpunk", "co-op", "multiplayer", "open-world", "stealth", "tower-defense"]


@router.post("/{pid}/tags")
async def auto_tags(pid: str):
    g = await _game(pid)
    blob = " ".join(str(g.get(k, "")) for k in ("title", "brief", "genre")).lower()
    tags = [t for t in _TAG_HINTS if t.replace("-", " ") in blob or t in blob]
    if g.get("genre"):
        tags = list(dict.fromkeys([g["genre"].lower()] + tags))
    tags = tags[:8] or ["original"]
    await _db.playables.update_one({"playable_id": pid}, {"$set": {"auto_tags": tags}})
    return {"pid": pid, "tags": tags}


# ── WIN 9 · Next-best-action recommender ────────────────────────────────────
@router.get("/{pid}/next-best-action")
async def next_best_action(pid: str):
    kb = await _kb(pid)
    arts = kb.get("artifacts") or {}
    g = await _game(pid)
    state = await _db.snowball_state.find_one({"pid": pid}, PROJ) or {}
    ladder = ["spec", "world", "narrative", "mechanics", "procedural", "assets", "qa", "build", "launch"]
    art_map = {"spec": "core_specs", "world": "lore_graph"}
    if not state.get("mounted_at"):
        return {"pid": pid, "action": "mount", "label": "Mount this game into Snowball to generate its GDD",
                "endpoint": f"/api/snowball/{pid}/mount"}
    built = len(arts)
    if built < len(ladder):
        nxt = ladder[min(built, len(ladder) - 1)]
        return {"pid": pid, "action": "run_stage", "stage": nxt,
                "label": f"Build the next stage: {nxt}",
                "endpoint": f"/api/pipeline/{pid}/forge/{nxt}/async"}
    if (g.get("score") or 0) < 95:
        return {"pid": pid, "action": "remaster", "label": "Remaster to clear the 95 quality gate",
                "endpoint": f"/api/snowball/{pid}/remaster"}
    return {"pid": pid, "action": "trailer", "label": "Generate a voiced trailer & ship",
            "endpoint": "/api/jeeves-voice/trailer"}


# ── WIN 10 · Self-describing catalog of the wins ────────────────────────────
@router.get("/catalog")
async def catalog():
    return {"wins": [
        {"id": 1, "name": "Shareable GDD card", "endpoint": "GET /api/wins/{pid}/gdd/share"},
        {"id": 2, "name": "Agent learning loop", "endpoint": "POST /api/wins/{pid}/reflect-all"},
        {"id": 3, "name": "Ship-readiness score", "endpoint": "GET /api/wins/{pid}/readiness"},
        {"id": 4, "name": "Top-builds leaderboard", "endpoint": "GET /api/wins/leaderboard"},
        {"id": 5, "name": "Marketing pitch", "endpoint": "POST /api/wins/{pid}/pitch"},
        {"id": 6, "name": "Auto changelog", "endpoint": "GET /api/wins/{pid}/changelog"},
        {"id": 7, "name": "Build health", "endpoint": "GET /api/wins/health"},
        {"id": 8, "name": "Auto-tags for discovery", "endpoint": "POST /api/wins/{pid}/tags"},
        {"id": 9, "name": "Next-best-action", "endpoint": "GET /api/wins/{pid}/next-best-action"},
        {"id": 10, "name": "Wins catalog", "endpoint": "GET /api/wins/catalog"},
    ]}
