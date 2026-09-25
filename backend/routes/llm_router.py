"""
╔══════════════════════════════════════════════════════════════════════════╗
║  PHASE I.1 — MODEL ROUTER & ENSEMBLE  (Genesis Engine)                     ║
║                                                                            ║
║  A single, cost/latency-aware entry point for every LLM call in the        ║
║  platform. Today ~30 route files each hand-roll `LlmChat(...).with_model`   ║
║  with a hardcoded model, ad-hoc retry, and zero caching/observability.     ║
║  This router centralises that:                                             ║
║                                                                            ║
║    • TASK-AWARE ROUTING — map an intent (code / reasoning / creative /     ║
║      fast / bulk / classify) to an ORDERED ensemble of (provider, model).  ║
║    • PROVIDER FALLBACK — on timeout/error, fail over to the next model in  ║
║      the ensemble instead of 502-ing the caller.                           ║
║    • ★ SOTA ENHANCEMENT — NORMALISED SEMANTIC CACHE: prompts are canon-    ║
║      icalised (whitespace/case/punctuation-folded) before hashing, so      ║
║      near-identical prompts collapse to one cache entry. Dependency-free,  ║
║      O(1), and it slashes cost + p50 latency on the repetitive prompts a   ║
║      generative game pipeline emits in bulk.                               ║
║    • COST/LATENCY TELEMETRY — every call (and cache hit) is metered →      ║
║      powers the /ai-router dashboard (calls, hit-rate, p50/p95, $ spent).  ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
import os
import re
import time
import json
import hashlib
import asyncio
from collections import OrderedDict
from datetime import datetime, timezone

from fastapi import APIRouter, Query
from pydantic import BaseModel
from core.databases import client as _SHARED_MONGO_CLIENT
from core.engine_client import EngineClient, EngineClientError
from core.engine_text import EngineTextError, EngineTextRequest, execute_engine_text

router = APIRouter(prefix="/api/llm-router", tags=["llm-router"])
_db = _SHARED_MONGO_CLIENT[os.environ.get("DB_NAME", "codedock")]
PROJ = {"_id": 0}

# ─── Legacy planning catalog ────────────────────────────────────────────────
# Entries may describe providers that are not currently declared for runtime
# execution. The executable ensemble is always filtered through AI_REGISTRY.
# cost_in / cost_out are legacy planning estimates only, never billing truth.
MODEL_CATALOG = {
    # ── OpenAI ──
    "gpt-5.5":              {"provider": "openai", "cost_in": 0.012, "cost_out": 0.060, "tier": "flagship"},
    "gpt-5.4":              {"provider": "openai", "cost_in": 0.005, "cost_out": 0.020, "tier": "flagship"},
    "gpt-5.4-mini":         {"provider": "openai", "cost_in": 0.0006, "cost_out": 0.0024, "tier": "fast"},
    "gpt-5-nano":           {"provider": "openai", "cost_in": 0.00005, "cost_out": 0.0004, "tier": "nano"},
    "gpt-4.1":              {"provider": "openai", "cost_in": 0.002, "cost_out": 0.008, "tier": "balanced"},
    "gpt-4.1-mini":         {"provider": "openai", "cost_in": 0.0004, "cost_out": 0.0016, "tier": "fast"},
    "gpt-4o":               {"provider": "openai", "cost_in": 0.0025, "cost_out": 0.010, "tier": "multimodal"},
    "o3":                   {"provider": "openai", "cost_in": 0.004, "cost_out": 0.016, "tier": "reasoning"},
    "o3-pro":               {"provider": "openai", "cost_in": 0.020, "cost_out": 0.080, "tier": "reasoning"},
    "o4-mini":              {"provider": "openai", "cost_in": 0.0011, "cost_out": 0.0044, "tier": "reasoning-fast"},
    # ── Anthropic ──
    "claude-opus-4-8":      {"provider": "anthropic", "cost_in": 0.015, "cost_out": 0.075, "tier": "flagship"},
    "claude-opus-4-7":      {"provider": "anthropic", "cost_in": 0.015, "cost_out": 0.075, "tier": "reasoning"},
    "claude-sonnet-4-6":    {"provider": "anthropic", "cost_in": 0.003, "cost_out": 0.015, "tier": "balanced"},
    "claude-haiku-4-5-20251001": {"provider": "anthropic", "cost_in": 0.0008, "cost_out": 0.004, "tier": "fast"},
    # ── Gemini ──
    "gemini-3.1-pro-preview": {"provider": "gemini", "cost_in": 0.0025, "cost_out": 0.010, "tier": "pro"},
    "gemini-2.5-pro":       {"provider": "gemini", "cost_in": 0.00125, "cost_out": 0.010, "tier": "pro"},
    "gemini-3.5-flash":     {"provider": "gemini", "cost_in": 0.0003, "cost_out": 0.0012, "tier": "fast"},
    "gemini-3-flash-preview": {"provider": "gemini", "cost_in": 0.0002, "cost_out": 0.001, "tier": "bulk"},
}

# ─── Routing policy: task → ordered planning candidates ────────────────────
# Cross-provider names remain useful as a future routing plan, but only models
# owned by the active declared provider are executable. Adding another provider
# requires a declared adapter + architecture receipt before it becomes eligible.
ROUTING_POLICY = {
    "code":            ["claude-sonnet-4-6", "gpt-5.4", "gemini-3.1-pro-preview"],
    "reasoning":       ["o3", "claude-opus-4-7", "gpt-5.5", "gemini-3.1-pro-preview"],
    "deep_reasoning":  ["claude-opus-4-8", "o3-pro", "gpt-5.5"],
    "creative":        ["gpt-5.4", "claude-sonnet-4-6", "gemini-3.1-pro-preview"],
    "multimodal":      ["gpt-4o", "gemini-3.1-pro-preview", "claude-sonnet-4-6"],
    "fast":            ["gpt-5.4-mini", "claude-haiku-4-5-20251001", "gemini-3.5-flash"],
    "classify":        ["gpt-5-nano", "gemini-3-flash-preview", "gpt-5.4-mini"],
    "bulk":            ["gemini-3-flash-preview", "gpt-5-nano", "gemini-3.5-flash"],
    "balanced":        ["gpt-4.1", "claude-sonnet-4-6", "gemini-2.5-pro"],
    "default":         ["gpt-5.4", "claude-sonnet-4-6", "gemini-3.1-pro-preview"],

    # ── GAME-SPECIFIC AI ROUTES ──────────────────────────────────────────
    # Each game-dev concern is mapped to the model ensemble best suited for it
    # (reasoning-heavy concerns → o3 / Opus; creative → GPT-5.4 / Sonnet; bulk
    # naming/tutorial → mini/haiku/flash). All provider-diverse for resilience.
    "gameplay_code":   ["claude-sonnet-4-6", "gpt-5.4", "gemini-3.1-pro-preview"],
    "shader_vfx":      ["gpt-5.4", "claude-sonnet-4-6", "gemini-3.1-pro-preview"],
    "level_design":    ["gpt-5.4", "gemini-3.1-pro-preview", "claude-sonnet-4-6"],
    "narrative_quest": ["claude-opus-4-7", "gpt-5.4", "gemini-3.1-pro-preview"],
    "npc_dialogue":    ["gpt-5.4", "claude-sonnet-4-6", "gemini-3.5-flash"],
    "npc_behavior_ai": ["o3", "claude-opus-4-7", "gpt-5.5"],
    "game_balance":    ["o3", "gpt-5.4", "gemini-3.1-pro-preview"],
    "economy_design":  ["o3", "claude-sonnet-4-6", "gpt-5.4"],
    "procedural_assets":["gemini-3.1-pro-preview", "gpt-5.4", "claude-sonnet-4-6"],
    "game_design_doc": ["claude-opus-4-7", "gpt-5.5", "o3"],
    "playtest_qa":     ["o3", "claude-sonnet-4-6", "gpt-5.4-mini"],
    "bug_fix":         ["claude-sonnet-4-6", "gpt-5.4", "o4-mini"],
    "naming_lore":     ["gpt-5.4-mini", "claude-haiku-4-5-20251001", "gemini-3.5-flash"],
    "audio_design":    ["gpt-5.4", "claude-sonnet-4-6", "gemini-3.1-pro-preview"],
    "tutorial_onboarding": ["gpt-5.4-mini", "claude-haiku-4-5-20251001", "gemini-3.5-flash"],
}

# ─── Game-specific AI task catalog (label + what each route is tuned for) ───
# Powers the /game-tasks endpoint and the /game/generate convenience API so the
# Galaxy Studio pipeline can dispatch every generation concern to the best AI.
GAME_TASKS = {
    "gameplay_code":   {"label": "Gameplay Code", "icon": "🎮", "about": "Core mechanics, controllers, game-loop logic."},
    "shader_vfx":      {"label": "Shaders & VFX", "icon": "✨", "about": "Shaders, particle systems, visual juice."},
    "level_design":    {"label": "Level Design", "icon": "🗺️", "about": "Layouts, encounter pacing, world graphs."},
    "narrative_quest": {"label": "Narrative & Quests", "icon": "📜", "about": "Branching story, quest graphs, lore arcs."},
    "npc_dialogue":    {"label": "NPC Dialogue", "icon": "💬", "about": "Persona-driven, emotion-aware dialogue trees."},
    "npc_behavior_ai": {"label": "NPC Behavior AI", "icon": "🧠", "about": "Behavior trees, utility AI, decision logic."},
    "game_balance":    {"label": "Game Balance", "icon": "⚖️", "about": "Tuning curves, difficulty, fairness analysis."},
    "economy_design":  {"label": "Economy Design", "icon": "💰", "about": "Currencies, sinks/faucets, progression econ."},
    "procedural_assets":{"label": "Procedural Assets", "icon": "🧬", "about": "Meshes, textures, material/recipe catalogs."},
    "game_design_doc": {"label": "Game Design Doc", "icon": "📐", "about": "Full GDD synthesis from a brief."},
    "playtest_qa":     {"label": "Playtest & QA", "icon": "🔍", "about": "Repro steps, edge cases, balance critique."},
    "bug_fix":         {"label": "Bug Fix", "icon": "🐛", "about": "Diagnose + patch gameplay/code defects."},
    "naming_lore":     {"label": "Naming & Lore", "icon": "🏷️", "about": "Item/character/place names, micro-lore."},
    "audio_design":    {"label": "Audio Design", "icon": "🎵", "about": "Adaptive music briefs, SFX direction."},
    "tutorial_onboarding": {"label": "Tutorial & Onboarding", "icon": "🎓", "about": "Teaching flows, hints, FTUE copy."},
}

DEFAULT_TIMEOUT_S = float(os.environ.get("LLM_ROUTER_TIMEOUT_S", "60"))
CACHE_TTL_S = int(os.environ.get("LLM_ROUTER_CACHE_TTL_S", "3600"))
CACHE_MAX = int(os.environ.get("LLM_ROUTER_CACHE_MAX", "512"))


def _engine_available() -> bool:
    try:
        return EngineClient.from_env() is not None
    except EngineClientError:
        return False


def _active_provider_id() -> str:
    return "skeleton-engine"


def _provider_status() -> dict:
    available = _engine_available()
    return {
        "active": "skeleton-engine",
        "available": available,
        "providers": [
            {
                "id": "skeleton-engine",
                "available": available,
                "active": True,
                "ownership": "engine-process",
            }
        ],
    }


def _model_is_executable(model: str) -> bool:
    # Vendor/model selection is engine-owned. Catalog entries are planning metadata.
    return False


def _executable_ensemble(task: str, pinned_model: str = "") -> list[str]:
    del task
    if pinned_model:
        return []
    return ["engine-routed"] if _engine_available() else []


def _catalog_view() -> dict[str, dict]:
    return {
        model: {
            **meta,
            "declared": False,
            "executable": False,
            "execution_owner": "skeleton-engine",
        }
        for model, meta in MODEL_CATALOG.items()
    }


# ════════════════════ Normalised semantic cache ════════════════════
_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s]")


def _canonical(text: str) -> str:
    """Fold whitespace, case and punctuation so near-identical prompts share a
    cache slot. Cheap stand-in for embedding similarity that catches the bulk
    of real-world duplicate prompts (re-runs, retries, templated generation)."""
    t = (text or "").lower().strip()
    t = _PUNCT.sub(" ", t)
    t = _WS.sub(" ", t)
    return t.strip()


def _cache_key(task: str, system: str, prompt: str) -> str:
    blob = f"{task}\x1f{_canonical(system)}\x1f{_canonical(prompt)}"
    return hashlib.sha256(blob.encode()).hexdigest()


class _LRUCache:
    """Tiny TTL + LRU cache. In-process; resets on reload (fine for a hot cache)."""
    def __init__(self, maxsize: int, ttl: int):
        self.maxsize, self.ttl = maxsize, ttl
        self._d: "OrderedDict[str, tuple]" = OrderedDict()

    def get(self, key):
        item = self._d.get(key)
        if not item:
            return None
        ts, val = item
        if time.time() - ts > self.ttl:
            self._d.pop(key, None)
            return None
        self._d.move_to_end(key)
        return val

    def set(self, key, val):
        self._d[key] = (time.time(), val)
        self._d.move_to_end(key)
        while len(self._d) > self.maxsize:
            self._d.popitem(last=False)

    def clear(self):
        n = len(self._d)
        self._d.clear()
        return n


_CACHE = _LRUCache(CACHE_MAX, CACHE_TTL_S)

# In-process counters (the durable per-call log lives in Mongo for the dashboard)
_STATS = {"calls": 0, "cache_hits": 0, "fallbacks": 0, "errors": 0}


def _estimate_cost(model: str, prompt_chars: int, out_chars: int) -> float:
    """~4 chars/token heuristic → USD using MODEL_CATALOG list prices."""
    meta = MODEL_CATALOG.get(model, {})
    tok_in = prompt_chars / 4 / 1000
    tok_out = out_chars / 4 / 1000
    return round(tok_in * meta.get("cost_in", 0) + tok_out * meta.get("cost_out", 0), 6)


async def _log_call(rec: dict):
    try:
        await _db.llm_router_calls.insert_one({**rec, "ts": datetime.now(timezone.utc).isoformat()})
    except Exception:
        pass


async def route_complete(task: str, prompt: str, system: str = "",
                         session_id: str = "", timeout_s: float = None,
                         use_cache: bool = True, model: str = "") -> dict:
    """Execute one compatibility completion through the canonical engine.

    The legacy model catalog remains planning metadata only. Provider/model
    selection and failover are engine-owned; this route does not create a
    second provider runtime or pretend to pin a vendor model locally.
    """
    task = (task or "default").lower()
    timeout_s = timeout_s or DEFAULT_TIMEOUT_S
    _STATS["calls"] += 1

    key = _cache_key(task, system, prompt)
    if use_cache:
        hit = _CACHE.get(key)
        if hit is not None:
            _STATS["cache_hits"] += 1
            await _log_call({
                "task": task,
                "model": hit["model"],
                "provider": hit["provider"],
                "cached": True,
                "latency_ms": 0,
                "est_cost_usd": 0.0,
            })
            return {**hit, "cached": True, "latency_ms": 0, "est_cost_usd": 0.0}

    if model:
        _STATS["errors"] += 1
        return {
            "content": "",
            "error": "model pinning is owned by the Skeleton engine",
            "error_code": "model_pinning_unavailable",
            "model": model if model in MODEL_CATALOG else None,
            "provider": "skeleton-engine",
            "cached": False,
            "task": task,
        }

    identity = hashlib.sha256(
        json.dumps(
            {
                "task": task,
                "system": system,
                "prompt": prompt,
                "session_id": session_id,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    started = time.time()
    try:
        response = await asyncio.wait_for(
            execute_engine_text(
                EngineTextRequest(
                    instructions=system or "You are a helpful assistant.",
                    prompt=prompt,
                    idempotency_key="llm-router:" + identity,
                    actor_id="llm-router",
                    capability="assistant.compat",
                    verification_profile="assistant_proposal",
                    max_output_tokens=8192,
                )
            ),
            timeout=timeout_s,
        )
    except (EngineTextError, TimeoutError, asyncio.TimeoutError):
        _STATS["errors"] += 1
        await _log_call({
            "task": task,
            "model": "engine-routed",
            "provider": "skeleton-engine",
            "cached": False,
            "error": "engine_request_failed",
        })
        return {
            "content": "",
            "error": "engine_request_failed",
            "error_code": "engine_unavailable",
            "model": "engine-routed",
            "provider": "skeleton-engine",
            "cached": False,
            "task": task,
            "attempts": 1,
        }

    latency_ms = int((time.time() - started) * 1000)
    result = {
        "content": response.text,
        "model": "engine-routed",
        "provider": "skeleton-engine",
        "cached": False,
        "latency_ms": latency_ms,
        "est_cost_usd": 0.0,
        "attempts": 1,
        "task": task,
    }
    if use_cache:
        _CACHE.set(
            key,
            {
                "content": response.text,
                "model": "engine-routed",
                "provider": "skeleton-engine",
                "task": task,
            },
        )
    await _log_call(result)
    return result


# ════════════════════════════ API surface ════════════════════════════
class CompleteBody(BaseModel):
    task: str = "default"
    prompt: str
    system: str = ""
    session_id: str = ""
    use_cache: bool = True
    model: str = ""


@router.get("/policy")
async def get_policy():
    """Routing policy + model catalog (for the dashboard + transparency)."""
    return {
        "policy": {
            task: _executable_ensemble(task)
            for task in ROUTING_POLICY
        },
        "planning_policy": ROUTING_POLICY,
        "models": _catalog_view(),
        "provider": _provider_status(),
        "key_configured": _engine_available(),
        "cache": {"ttl_s": CACHE_TTL_S, "max": CACHE_MAX, "size": len(_CACHE._d)},
    }


@router.post("/complete")
async def complete(body: CompleteBody):
    if len(body.prompt) > 40_000:
        return {"error": "prompt exceeds 40k char limit"}
    return await route_complete(body.task, body.prompt, body.system,
                                body.session_id, use_cache=body.use_cache, model=body.model)


@router.get("/stats")
async def stats():
    """Aggregated router telemetry for the dashboard."""
    total = await _db.llm_router_calls.count_documents({})
    cached = await _db.llm_router_calls.count_documents({"cached": True})
    errors = await _db.llm_router_calls.count_documents({"error": {"$exists": True}})

    by_model = await _db.llm_router_calls.aggregate([
        {"$match": {"model": {"$ne": None}}},
        {"$group": {"_id": "$model", "calls": {"$sum": 1},
                    "cost": {"$sum": "$est_cost_usd"},
                    "avg_latency": {"$avg": "$latency_ms"}}},
        {"$sort": {"calls": -1}},
    ]).to_list(20)

    by_task = await _db.llm_router_calls.aggregate([
        {"$group": {"_id": "$task", "calls": {"$sum": 1},
                    "cost": {"$sum": "$est_cost_usd"}}},
        {"$sort": {"calls": -1}},
    ]).to_list(20)

    total_cost = sum((m.get("cost") or 0) for m in by_model)
    return {
        "total_calls": total,
        "cache_hits": cached,
        "cache_hit_rate": round(cached / total * 100, 1) if total else 0.0,
        "errors": errors,
        "est_total_cost_usd": round(total_cost, 4),
        "live_counters": _STATS,
        "by_model": [{"model": m["_id"], "calls": m["calls"],
                      "cost_usd": round(m.get("cost") or 0, 5),
                      "avg_latency_ms": int(m.get("avg_latency") or 0)} for m in by_model],
        "by_task": [{"task": t["_id"] or "default", "calls": t["calls"],
                     "cost_usd": round(t.get("cost") or 0, 5)} for t in by_task],
    }


@router.post("/cache/clear")
async def cache_clear():
    n = _CACHE.clear()
    return {"cleared": n}


# ════════════════════════ GAME-SPECIFIC AI API ════════════════════════
class GameGenBody(BaseModel):
    game_task: str
    prompt: str
    system: str = ""
    session_id: str = ""
    use_cache: bool = True


@router.get("/game-tasks")
async def game_tasks():
    """Catalog of game-dev AI routes + the model ensemble each one dispatches to."""
    return {
        "tasks": [
            {
                "task": k,
                **meta,
                "ensemble": _executable_ensemble(k),
                "planning_ensemble": ROUTING_POLICY.get(k, []),
            }
            for k, meta in GAME_TASKS.items()
        ],
        "count": len(GAME_TASKS),
    }


@router.post("/game/generate")
async def game_generate(body: GameGenBody):
    """Dispatch a game-dev concern through the declared provider ensemble.

    Planning metadata may include future providers, but execution is restricted
    to providers declared by the active construction contract. The shared cache
    and telemetry record the provider/model that actually answered."""
    task = (body.game_task or "").lower()
    if task not in GAME_TASKS:
        return {"error": f"unknown game_task '{task}'", "valid_tasks": list(GAME_TASKS.keys())}
    if len(body.prompt) > 40_000:
        return {"error": "prompt exceeds 40k char limit"}
    sys = body.system or f"You are an expert game developer specialising in: {GAME_TASKS[task]['about']}"
    result = await route_complete(task, body.prompt, sys, body.session_id, use_cache=body.use_cache)
    return {**result, "game_task": task, "task_label": GAME_TASKS[task]["label"]}
