"""
🎬 MODE SELECTION — Stage 1 of the AI Game-Builder pipeline (sets constraints & inheritance first).

Twelve creation modes that frame a NEW game relative to an existing one (sequel, prequel,
expansion, series-variant, conclusion, remaster, spin-off, crossover, reboot, DLC, demake,
what-if). Picking a mode against a parent game deterministically assembles a constraint- and
inheritance-aware brief (world + characters + mechanics carried forward as the mode dictates),
which the client then feeds to /api/playable/generate/async. No LLM here — pure, fast assembly
so the downstream codegen inherits a consistent canon.
"""
from __future__ import annotations

import os
from fastapi import APIRouter
from pydantic import BaseModel

from core.databases import client as _MONGO

router = APIRouter(prefix="/api/modes", tags=["modes"])
_db = _MONGO[os.environ.get("DB_NAME", "test_database")]

# id, label, emoji, what it inherits, the creative directive layered on top
MODES = [
    {"id": "sequel", "label": "Sequel", "emoji": "⏭️", "inherit": "world+characters+mechanics",
     "directive": "Continue the canon AFTER the original — advance the timeline, evolve returning characters, raise the stakes."},
    {"id": "prequel", "label": "Prequel", "emoji": "⏮️", "inherit": "world+mechanics",
     "directive": "Tell an origin story set BEFORE the original — seed events the original later pays off; keep the world consistent."},
    {"id": "expansion", "label": "Expansion", "emoji": "🧩", "inherit": "world+characters+mechanics",
     "directive": "Add a new region/chapter to the SAME game — new content, same core loop and systems."},
    {"id": "series_variant", "label": "Series Variant", "emoji": "🔀", "inherit": "mechanics",
     "directive": "A sibling title in the same series — keep the signature mechanics, fresh setting and cast."},
    {"id": "conclusion", "label": "Conclusion", "emoji": "🏁", "inherit": "world+characters+mechanics",
     "directive": "The grand FINALE — resolve every arc, escalate to a climactic endgame, pay off the canon."},
    {"id": "remaster", "label": "Remaster", "emoji": "✨", "inherit": "world+characters+mechanics+story",
     "directive": "Faithfully modernise the original — same content and story, richer juice, polish and feel."},
    {"id": "spinoff", "label": "Spin-off", "emoji": "🌱", "inherit": "world",
     "directive": "Follow a side character or sub-faction in the same world — a different genre/loop is welcome."},
    {"id": "crossover", "label": "Crossover", "emoji": "🤝", "inherit": "characters+mechanics",
     "directive": "Fuse this game's cast/mechanics with a fresh world — celebrate the mashup."},
    {"id": "reboot", "label": "Reboot", "emoji": "♻️", "inherit": "theme",
     "directive": "Reimagine from scratch — keep only the core THEME/premise; new world, cast and systems."},
    {"id": "dlc_pack", "label": "DLC Pack", "emoji": "📦", "inherit": "world+characters+mechanics",
     "directive": "A tight bonus pack — a focused new challenge/mode bolted onto the existing game."},
    {"id": "demake", "label": "Demake", "emoji": "🕹️", "inherit": "world+characters+story",
     "directive": "Reinterpret as a retro/minimalist micro-game — same soul, simpler systems and presentation."},
    {"id": "what_if", "label": "What-If", "emoji": "❓", "inherit": "world+characters",
     "directive": "An alternate-reality twist — change one pivotal premise and explore the consequences."},
]
_BY_ID = {m["id"]: m for m in MODES}


class ForgeBriefBody(BaseModel):
    parent_id: str
    mode: str
    extra: str = ""   # optional creator nudge


@router.get("/options")
async def options():
    """🎬 The 12 creation modes (Stage 1)."""
    return {"modes": MODES, "count": len(MODES)}


@router.post("/forge-brief")
async def forge_brief(body: ForgeBriefBody):
    """Assemble a constraint + inheritance-aware brief from a parent game for the chosen mode.
    Returns {brief, title, mode, inherited} — feed `brief`/`title` straight to /playable generate."""
    mode = _BY_ID.get(body.mode)
    if not mode:
        return {"error": "unknown mode", "valid": list(_BY_ID.keys())}
    parent = await _db.playables.find_one(
        {"playable_id": body.parent_id},
        {"_id": 0, "title": 1, "brief": 1, "genre": 1, "forged_from": 1})
    if not parent:
        return {"error": "parent game not found"}

    ptitle = parent.get("title") or "the original"
    inherit = mode["inherit"]
    parts = [
        f"MODE: {mode['label']} ({mode['emoji']}). {mode['directive']}",
        f"PARENT GAME: \"{ptitle}\"" + (f" — {parent['brief']}" if parent.get("brief") else "")
        + (f" (genre: {parent['genre']})" if parent.get("genre") else ""),
        f"INHERITANCE CONTRACT — carry forward: {inherit.replace('+', ', ')}. "
        "Stay strictly consistent with whatever is inherited; only change what this mode allows.",
    ]

    # Pull canon from the Knowledge Base when the mode inherits world/characters/story.
    inherited: dict = {"mode": mode["id"], "from": ptitle, "contract": inherit}
    pull = ("world" in inherit or "characters" in inherit or "story" in inherit)
    kbdoc = await _db.game_kb.find_one({"game_id": body.parent_id}, {"_id": 0, "artifacts": 1}) if pull else None
    arts = (kbdoc or {}).get("artifacts") or {}
    quest_db = arts.get("quest_db") or {}
    lore = arts.get("lore_graph") or {}
    if arts:
        if "characters" in inherit:
            bibles = quest_db.get("character_bibles") or quest_db.get("characters") or []
            names = [c.get("name") for c in bibles[:5] if isinstance(c, dict) and c.get("name")]
            if names:
                parts.append("RETURNING/CANON CHARACTERS: " + ", ".join(names) + ".")
                inherited["characters"] = names
        if "story" in inherit or "world" in inherit:
            qt = [q.get("title") for q in (quest_db.get("quests") or [])[:4]
                  if isinstance(q, dict) and q.get("title")]
            if qt:
                parts.append("CANON STORY BEATS to honour: " + "; ".join(qt) + ".")
                inherited["quests"] = qt
        if "world" in inherit:
            facs = [f.get("name") for f in (lore.get("factions") or [])[:4]
                    if isinstance(f, dict) and f.get("name")]
            if facs:
                parts.append("CANON FACTIONS: " + ", ".join(facs) + ".")
                inherited["factions"] = facs
            setting = lore.get("setting") or (lore.get("world") or {}).get("setting")
            if isinstance(setting, str) and setting.strip():
                parts.append("CANON SETTING: " + setting.strip()[:200])

    if body.extra.strip():
        parts.append("CREATOR NOTE: " + body.extra.strip()[:300])
    parts.append("Build a runnable, juicy mini-game that satisfies the mode while respecting the inheritance contract.")

    title = f"{ptitle}: {mode['label']}" if mode["id"] not in ("remaster", "reboot") else (
        f"{ptitle} — {'Remastered' if mode['id'] == 'remaster' else 'Reboot'}")
    return {"brief": "\n".join(parts), "title": title[:80], "mode": mode["id"], "inherited": inherited}
