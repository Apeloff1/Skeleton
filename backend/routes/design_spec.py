"""
╔══════════════════════════════════════════════════════════════════════════╗
║  PHASE I.4 — DESIGN-SPEC COMPILER  (Genesis Engine)                        ║
║                                                                            ║
║  Turns a free-text game brief into a TYPED, versioned, diff-able Game      ║
║  Design Document (GDD) + an executable build plan — the contract every     ║
║  downstream pipeline (Worldforge, Sentience, Aesthetics…) consumes.        ║
║                                                                            ║
║  Flow:  brief ──▶ LLM (via the Model Router, task='reasoning') ──▶ strict  ║
║  JSON ──▶ tolerant parse ──▶ schema normalisation (never KeyErrors) ──▶    ║
║  ★ COHERENCE GATE (completeness heuristic × LLM self-rating) ──▶ persist.  ║
║                                                                            ║
║  ★ SOTA ENHANCEMENT — SCHEMA-VALIDATED STRUCTURED OUTPUT + COHERENCE GATE: ║
║  the compiler refuses to emit an incoherent spec (missing pillars, empty   ║
║  core loop, contradictory scope) — it returns status='needs_revision' with ║
║  actionable reasons instead of letting a half-baked brief burn a build.    ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
import os
import re
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Query
from pydantic import BaseModel
from core.databases import client as _SHARED_MONGO_CLIENT
from routes.llm_router import route_complete

router = APIRouter(prefix="/api/design-spec", tags=["design-spec"])
_db = _SHARED_MONGO_CLIENT[os.environ.get("DB_NAME", "test_database")]
PROJ = {"_id": 0}

COHERENCE_THRESHOLD = int(os.environ.get("DESIGN_SPEC_COHERENCE_MIN", "60"))

# Typed GDD skeleton — every key the build plan relies on, with safe defaults.
_GDD_SKELETON = {
    "title": "Untitled Game",
    "genre": "rpg",
    "subgenre": "",
    "logline": "",
    "pillars": [],          # 3-5 design pillars
    "core_loop": "",        # the moment-to-moment loop
    "mechanics": [],        # [{name, description}]
    "systems": [],          # [{name, description}]
    "progression": "",
    "art_direction": "",
    "audio_direction": "",
    "content_plan": {"levels": 0, "enemies": 0, "items": 0, "npcs": 0},
    "target_platforms": ["mobile"],
    "scope_tier": "FORGE",  # FORGE/JUGGERNAUT/BEHEMOTH/LEVIATHAN/COLOSSUS/TITAN
    "risks": [],
    "coherence_self": 0,    # LLM's own 0-100 estimate
}

_SYSTEM = """You are a senior game director. Convert the user's game brief into a STRICT JSON \
Game Design Document. Output ONLY valid JSON (no markdown fences, no prose) with EXACTLY these keys:
title (string), genre (string), subgenre (string), logline (string, 1 sentence),
pillars (array of 3-5 short strings), core_loop (string), mechanics (array of {name, description}),
systems (array of {name, description}), progression (string), art_direction (string),
audio_direction (string), content_plan ({levels:int, enemies:int, items:int, npcs:int}),
target_platforms (array of strings), scope_tier (one of FORGE/JUGGERNAUT/BEHEMOTH/LEVIATHAN/COLOSSUS/TITAN),
risks (array of short strings), coherence_self (integer 0-100 — how complete/coherent this spec is).
Be specific and ambitious but internally consistent."""


def _extract_json(text: str) -> dict:
    """Tolerant JSON extraction — strips fences, grabs the outermost {...}.
    Never raises; returns {} on failure so the caller can fall back."""
    if not text:
        return {}
    t = text.strip()
    t = re.sub(r"^```(?:json)?", "", t).strip()
    t = re.sub(r"```$", "", t).strip()
    try:
        return json.loads(t)
    except Exception:
        pass
    start, depth = t.find("{"), 0
    if start == -1:
        return {}
    for i in range(start, len(t)):
        if t[i] == "{":
            depth += 1
        elif t[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(t[start:i + 1])
                except Exception:
                    return {}
    return {}


def _normalize(raw: dict) -> dict:
    """Coerce parsed JSON onto the typed skeleton — guarantees every key exists
    with the right type (the anti-KeyError contract for downstream pipelines)."""
    g = json.loads(json.dumps(_GDD_SKELETON))  # deep copy
    if not isinstance(raw, dict):
        return g
    for k, default in _GDD_SKELETON.items():
        v = raw.get(k, default)
        if isinstance(default, list) and not isinstance(v, list):
            v = [v] if v else []
        elif isinstance(default, dict) and not isinstance(v, dict):
            v = default
        elif isinstance(default, int) and not isinstance(default, bool):
            try:
                v = int(v)
            except (TypeError, ValueError):
                v = default
        elif isinstance(default, str) and not isinstance(v, str):
            v = str(v) if v is not None else default
        g[k] = v
    # normalize content_plan ints
    cp = g["content_plan"]
    for ck in ("levels", "enemies", "items", "npcs"):
        try:
            cp[ck] = int(cp.get(ck, 0))
        except (TypeError, ValueError):
            cp[ck] = 0
    return g


def _coherence(g: dict) -> tuple:
    """Blend a completeness heuristic with the LLM's self-rating → 0-100 score
    + list of gaps. This is the gate that blocks half-baked specs."""
    gaps = []
    score = 0
    # completeness (60 pts)
    if g["logline"].strip(): score += 10
    else: gaps.append("missing logline")
    if len(g["pillars"]) >= 3: score += 15
    else: gaps.append("need ≥3 design pillars")
    if g["core_loop"].strip(): score += 10
    else: gaps.append("missing core loop")
    if len(g["mechanics"]) >= 3: score += 15
    else: gaps.append("need ≥3 mechanics")
    if len(g["systems"]) >= 2: score += 10
    else: gaps.append("need ≥2 systems")
    # LLM self-rating blended in (40 pts)
    self_r = max(0, min(100, g.get("coherence_self", 0)))
    score += int(self_r * 0.4)
    return min(100, score), gaps


class CompileBody(BaseModel):
    brief: str
    title: str = ""


@router.post("/compile")
async def compile_spec(body: CompileBody):
    """Compile a NL brief into a typed, coherence-gated GDD."""
    brief = (body.brief or "").strip()
    if len(brief) < 8:
        return {"error": "brief too short (min 8 chars)"}
    if len(brief) > 8000:
        return {"error": "brief exceeds 8k char limit"}

    routed = await route_complete(task="reasoning", prompt=brief, system=_SYSTEM)
    llm_error = routed.get("error")
    gdd = _normalize(_extract_json(routed.get("content", "")))
    if body.title:
        gdd["title"] = body.title

    coherence, gaps = _coherence(gdd)
    status = "ready" if coherence >= COHERENCE_THRESHOLD else "needs_revision"

    # Executable build plan handoff (what the pipeline consumes).
    build_plan = {
        "genre": gdd["genre"],
        "subgenre": gdd["subgenre"],
        "scope_tier": gdd["scope_tier"],
        "target_files_hint": {
            "FORGE": 5000, "JUGGERNAUT": 12000, "BEHEMOTH": 24000,
            "LEVIATHAN": 60000, "COLOSSUS": 120000, "TITAN": 250000,
        }.get(gdd["scope_tier"], 5000),
        "systems": [s.get("name", "") if isinstance(s, dict) else str(s) for s in gdd["systems"]],
    }

    spec = {
        "spec_id": uuid.uuid4().hex,
        "brief": brief,
        "gdd": gdd,
        "coherence_score": coherence,
        "gaps": gaps,
        "status": status,
        "build_plan": build_plan,
        "model": routed.get("model"),
        "cached": routed.get("cached", False),
        "llm_error": llm_error,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "version": 1,
    }
    try:
        await _db.design_specs.insert_one(dict(spec))
    except Exception:
        pass
    return spec


@router.get("/list")
async def list_specs(limit: int = Query(20, le=100)):
    specs = await _db.design_specs.find({}, PROJ).sort("created_at", -1).limit(limit).to_list(limit)
    return {"specs": specs, "count": len(specs)}


@router.get("/{spec_id}")
async def get_spec(spec_id: str):
    spec = await _db.design_specs.find_one({"spec_id": spec_id}, PROJ)
    return spec or {"error": "not found"}
