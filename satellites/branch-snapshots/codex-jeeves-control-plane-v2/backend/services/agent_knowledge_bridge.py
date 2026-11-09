"""
agent_knowledge_bridge.py — Map each agent role to the knowledge collections
it should consult before formulating its response. Returns 1-3 representative
rows per relevant collection, formatted for prompt injection.

Role → DB map (the agent system grew from 4 roles to ~24 — this is a curated
"what would help this agent" lookup table):
"""
from __future__ import annotations
import os, asyncio
from motor.motor_asyncio import AsyncIOMotorClient
# ★ Consolidated 2026-02 — shared MongoDB client (lazy connect, fast timeouts)
from core.databases import client as _SHARED_MONGO_CLIENT
from typing import Any

_MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
_DB_NAME   = os.environ.get("DB_NAME", "test_database")
_client: AsyncIOMotorClient | None = None


def _db():
    global _client
    if _client is None:
        _client = _SHARED_MONGO_CLIENT  # consolidated → core.databases.client
    return _client[_DB_NAME]


# ─────────────────────────────────────────────────────────────────
# Role → collection map
# ─────────────────────────────────────────────────────────────────
ROLE_DB_MAP: dict[str, list[str]] = {
    # Game-side
    "planner":      ["build_recipes",        "game_design",       "design_patterns"],
    "architect":    ["design_patterns",      "engine_api",        "build_recipes"],
    "designer":     ["game_design",          "balance_curves",    "deep_lore"],
    "coder":        ["code_synthesis",       "github_code",       "engine_api"],
    "writer":       ["emotional_dialogue",   "deep_lore",         "director_pacing"],
    "asset_artist": ["procedural_assets",    "visual_juice",      "publishing_assets"],
    "audio":        ["audio_dsp",            "input_haptics"],
    "physics":      ["physics_materials_sim","engine_api"],
    "ecology":      ["ecosystems_biology",   "deep_lore"],
    "ai_designer":  ["ai_generative_weights","cognitive_psychographics"],

    # Quality / safety
    "reviewer":     ["code_synthesis",       "linting_formatters", "code_similarity_logic"],
    "tester":       ["qa_oracles",           "gamestate_schemas"],
    "qa":           ["qa_oracles",           "gamestate_schemas",  "bugfix_library"],
    "debugger":     ["bugfix_library",       "qa_oracles",         "ast_detection"],
    "security":     ["security_crypto",      "ast_detection"],
    "legal":        ["legal_compliance",     "mechanic_legal_paradox"],
    "optimizer":    ["build_recipes",        "training_recipes"],

    # Education
    "teacher":      ["patch_notes_curated",  "patch_notes_extended", "github_code"],
    "tutor":        ["patch_notes_curated",  "github_code"],
    "academic":     ["academic_frameworks",  "historical_meta"],

    # Meta / strategy
    "director":     ["director_pacing",      "build_recipes"],
    "researcher":   ["historical_meta",      "academic_frameworks"],
    "marketer":     ["publishing_assets",    "stylometric_fingerprint"],
}


# ─────────────────────────────────────────────────────────────────
# Fetch
# ─────────────────────────────────────────────────────────────────
async def fetch_for_role(role: str, topic: str = "", limit_per_coll: int = 2) -> dict:
    """Return up to `limit_per_coll` rows from each collection relevant to `role`."""
    role_norm = (role or "").lower().strip().replace("-", "_").replace(" ", "_")
    cols = ROLE_DB_MAP.get(role_norm, [])
    if not cols:
        # Fuzzy fallback — match substring
        for k, v in ROLE_DB_MAP.items():
            if k in role_norm or role_norm in k:
                cols = v
                break
    if not cols:
        return {"role": role, "rows": {}, "matched_collections": []}

    db = _db()
    rows_by_coll: dict[str, list] = {}
    for coll in cols:
        try:
            q = {}
            if topic:
                q = {"$text": {"$search": topic}} if False else {  # text index may not exist; fall back to regex
                    "$or": [
                        {"tags":     {"$regex": topic, "$options": "i"}},
                        {"keywords": {"$regex": topic, "$options": "i"}},
                        {"summary":  {"$regex": topic, "$options": "i"}},
                        {"name":     {"$regex": topic, "$options": "i"}},
                    ]
                }
            cur = db[coll].find(q, {"_id": 0}).limit(limit_per_coll)
            rows_by_coll[coll] = await cur.to_list(length=limit_per_coll)
            # If topic-filter returned nothing, take any rows (unfiltered)
            if not rows_by_coll[coll]:
                cur = db[coll].find({}, {"_id": 0}).limit(limit_per_coll)
                rows_by_coll[coll] = await cur.to_list(length=limit_per_coll)
        except Exception:
            rows_by_coll[coll] = []
    return {"role": role, "matched_collections": cols, "rows": rows_by_coll}


def format_for_prompt(bridge: dict, max_chars: int = 1200) -> str:
    """Compact knowledge-block ready to be injected into an agent system prompt."""
    rows = bridge.get("rows", {})
    if not rows:
        return ""
    out = "\n--- KNOWLEDGE BRIDGE ---\n"
    for coll, items in rows.items():
        if not items:
            continue
        out += f"[{coll}]\n"
        for item in items[:2]:
            # Pick the most informative field
            text = ""
            if isinstance(item, dict):
                for cand in ("summary", "description", "pattern", "rule", "lesson", "name", "title"):
                    if isinstance(item.get(cand), str):
                        text = item[cand]
                        break
                if not text:
                    text = str(item)
            else:
                text = str(item)
            text = text.replace("\n", " ")[:180]
            out += f"  • {text}\n"
        if len(out) > max_chars:
            break
    return out[:max_chars]
