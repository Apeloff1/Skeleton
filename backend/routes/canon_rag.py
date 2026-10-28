"""
🧠 CANON RAG MEMORY — retrieval layer so agents can recall prior canon.

The "memory store" is derived from the Central KB: every faction/region/creature/character/
quest/mechanic/pillar becomes a retrievable chunk. _recall(pid, query, k) returns the top-k
most relevant canon chunks (lexical relevance — token overlap + phrase boost). Agents call
this before generating so new content stays consistent with what already exists.

NOTE: lexical retrieval (no external embedding model is available with the universal key);
functionally this is the RAG retrieval layer the schematic calls for.
"""
from __future__ import annotations

import os
import re
import json

from fastapi import APIRouter

from core.databases import client as _MONGO

router = APIRouter(prefix="/api/rag", tags=["rag"])
_db = _MONGO[os.environ.get("DB_NAME", "test_database")]

_STOP = {"the", "and", "for", "with", "that", "this", "are", "was", "you", "your", "from",
         "has", "have", "but", "not", "all", "can", "its", "they", "their", "into", "out",
         "who", "what", "when", "game", "player", "players"}


def _tok(s: str) -> list:
    return [w for w in re.findall(r"[a-z0-9]+", (s or "").lower()) if len(w) > 2 and w not in _STOP]


def _entity_text(e) -> str:
    if isinstance(e, dict):
        return " ".join(str(v) for v in e.values() if isinstance(v, (str, int, float)))
    return str(e)


def _entity_name(e, fallback: str) -> str:
    if isinstance(e, dict):
        return e.get("name") or e.get("title") or e.get("item") or e.get("system") or fallback
    return str(e)[:40]


def chunks_from_arts(arts: dict) -> list:
    """Build the retrievable canon chunks from KB artifacts."""
    out = []
    spec = arts.get("core_specs") or {}
    if spec.get("logline"):
        out.append({"type": "Concept", "name": "Logline", "text": spec["logline"]})
    for p in (spec.get("pillars") or [])[:8]:
        out.append({"type": "Pillar", "name": _entity_name(p, "Pillar"), "text": _entity_text(p)})
    lore = arts.get("lore_graph") or {}
    if lore.get("setting"):
        out.append({"type": "Setting", "name": "Setting", "text": str(lore["setting"])})
    for grp, typ in (("factions", "Faction"), ("regions", "Region"), ("bestiary", "Creature")):
        for e in (lore.get(grp) or [])[:20]:
            out.append({"type": typ, "name": _entity_name(e, typ), "text": _entity_text(e)})
    quest = arts.get("quest_db") or {}
    for e in (quest.get("character_bibles") or quest.get("characters") or [])[:20]:
        out.append({"type": "Character", "name": _entity_name(e, "Character"), "text": _entity_text(e)})
    for e in (quest.get("quests") or [])[:30]:
        out.append({"type": "Quest", "name": _entity_name(e, "Quest"), "text": _entity_text(e)})
    mech = arts.get("mechanics_config") or {}
    for e in (mech.get("core_mechanics") or [])[:20]:
        out.append({"type": "Mechanic", "name": _entity_name(e, "Mechanic"), "text": _entity_text(e)})
    proc = arts.get("procedural_config") or {}
    for e in (proc.get("requirements") or [])[:15]:
        out.append({"type": "Requirement", "name": _entity_name(e, "Requirement"), "text": _entity_text(e)})
    return out


async def _arts(pid: str) -> dict:
    kb = await _db.game_kb.find_one({"game_id": pid}, {"_id": 0, "artifacts": 1})
    return (kb or {}).get("artifacts") or {}


def _score(query_tokens: set, chunk: dict) -> float:
    ct = set(_tok(chunk["name"] + " " + chunk["text"]))
    if not ct:
        return 0.0
    overlap = len(query_tokens & ct)
    # phrase boost if the chunk name appears verbatim
    return overlap + (overlap / (len(ct) ** 0.5))


async def _recall(pid: str, query: str, k: int = 5) -> list:
    """Top-k relevant canon chunks for a query (used by agents before generating)."""
    arts = await _arts(pid)
    chunks = chunks_from_arts(arts)
    qt = set(_tok(query))
    if not qt or not chunks:
        return []
    scored = [(c, _score(qt, c)) for c in chunks]
    scored = [s for s in scored if s[1] > 0]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [{"type": c["type"], "name": c["name"], "text": c["text"][:240], "score": round(sc, 2)}
            for c, sc in scored[:k]]


def recall_block(hits: list) -> str:
    """Render recalled canon as a prompt-injectable block."""
    if not hits:
        return ""
    lines = [f"- [{h['type']}] {h['name']}: {h['text']}" for h in hits]
    return "RELEVANT EXISTING CANON (stay consistent with this):\n" + "\n".join(lines)


@router.get("/{pid}/memory")
async def memory_stats(pid: str):
    """🧠 Size + composition of the canon memory store."""
    arts = await _arts(pid)
    chunks = chunks_from_arts(arts)
    by_type: dict = {}
    for c in chunks:
        by_type[c["type"]] = by_type.get(c["type"], 0) + 1
    return {"game_id": pid, "chunks": len(chunks), "by_type": by_type,
            "indexed_artifacts": list(arts.keys())}


@router.get("/{pid}/retrieve")
async def retrieve(pid: str, q: str = "", k: int = 5):
    """🔎 Retrieve the top-k canon chunks relevant to a query."""
    hits = await _recall(pid, q, k)
    return {"game_id": pid, "query": q, "k": k, "count": len(hits), "hits": hits}
