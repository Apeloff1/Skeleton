"""
╔════════════════════════════════════════════════════════════════════════╗
║  AGENT LEDGER — per-agent internal logs, specialization & contribution ║
║                                                                        ║
║  Every agent (swarm + collection) gets a capped append-only ledger     ║
║  stored in Mongo collection `agent_ledgers` (TTL & cap-guarded).       ║
║                                                                        ║
║  Each ledger entry records when the agent spoke in discourse:          ║
║     { agent_code, build_id, phase, layer, move, text, specialization,  ║
║       influence_score, whispered_to, timestamp }                       ║
║                                                                        ║
║  Helpers:                                                              ║
║     • log(entry)         — append one contribution                     ║
║     • notebook(code)     — read an agent's recent utterances           ║
║     • specialization(..) — pick domain-tuned spec tag for an utterance ║
║     • stats()            — aggregate: totals per agent, top-k talkers  ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations
import os
import time
import random
from typing import Any

from core.databases import get_sync_db

_db = get_sync_db()
_ledger = _db["agent_ledgers"]
_ledger.create_index([("agent_code", 1), ("timestamp", -1)])
_ledger.create_index([("build_id", 1)])

LEDGER_SOFT_CAP = int(os.environ.get("AGENT_LEDGER_CAP", "20000"))

# Specialization tags chosen per agent category — adds flavor to utterances.
_SPECIALIZATIONS = {
    "rendering":            ["hdr-pipeline", "ray-tracing", "tile-residency", "temporal-reprojection", "cluster-forward"],
    "shaders":              ["wgsl-spec", "hlsl-sm6", "glsl-4.6", "compute-parallelism", "descriptor-set-v2"],
    "animation":            ["mocap-cleanup", "blend-tree-2d", "procedural-locomotion", "facial-morph", "ragdoll-blend"],
    "physics":              ["continuous-sweep", "constraint-island", "pbd-xpbd", "sph-flip", "voronoi-fracture"],
    "ai_npc":               ["goap-htn", "utility-curves", "navmesh-detour", "perception-cone", "ocean-mood-model"],
    "networking":           ["rollback-ggpo", "deterministic-lockstep", "snapshot-delta", "anti-cheat", "eac-battleye"],
    "audio":                ["hrtf-ambisonic", "fmod-wwise", "dynamic-vertical", "rtpc-parameters", "vo-lip-sync"],
    "design":               ["verb-loops", "dda-mastery", "sink-source-economy", "scaffolded-tutorial", "juice-feedback"],
    "narrative":            ["ink-script", "yarn-spinner", "branching-flags", "faction-cascade", "voiceover-casting"],
    "level_design":         ["blockout-metrics", "hub-spoke", "portal-occlusion", "streaming-lod", "vertical-traversal"],
    "procgen":              ["wfc-collapse", "marching-cubes", "perlin-fbm", "markov-names", "loot-pity-tables"],
    "combat_controls":      ["frame-data", "cancel-chains", "parry-window", "input-buffer", "ranged-bloom"],
    "ui_ux":                ["focus-graph", "diegetic-hud", "toast-queue", "rtl-cjk", "coachmark-tutorial"],
    "tooling":              ["ci-pipeline", "asset-importer", "perforce-lfs", "telemetry-batching", "pix-renderdoc"],
    "platforms":            ["metal-vulkan", "steamworks", "eos-social", "dualsense-haptic", "openxr-comfort"],
    "liveops_monetization": ["battle-pass-curve", "ltv-cohort", "pricing-ab", "cosmetic-rotation", "live-events"],
    "qa_security":          ["fuzz-property", "soak-overnight", "crash-breakpad", "kernel-anticheat", "gdpr-coppa"],
    "math_cs":              ["quaternion-slerp", "bayes-monte-carlo", "spatial-octree", "simd-avx", "lock-free-ring"],
    "production":           ["sprint-retro", "risk-moscow", "vertical-slice", "burn-rate", "ip-licensing"],
    "era_esoteric":         ["nes-chr-rom", "snes-mode7", "ps1-vertex-jitter", "vr-90fps-comfort", "pico-8-fantasy"],
}


def pick_specialization(agent: dict, rng: random.Random | None = None) -> str:
    rng = rng or random.Random()
    cat = agent.get("category", "general")
    pool = _SPECIALIZATIONS.get(cat) or agent.get("expertise") or ["general-practice"]
    return rng.choice(pool)


def influence_score(agent: dict, move: str, layer: str) -> int:
    """Crude scoring: more senior roles + higher layers = more influence."""
    base = 1
    if layer == "legion":
        base += 3
    elif layer == "full_swarm":
        base += 2
    if move in ("arbitrates", "mandates", "synthesizes", "escalates"):
        base += 2
    if move in ("affirms", "harmonizes", "crystallizes"):
        base += 1
    seat = int(agent.get("team_seat", 5) or 5)
    if seat <= 2:
        base += 1  # team leaders / seniors
    return base


def log(entry: dict) -> None:
    """Append a contribution record. Adds timestamp if missing."""
    entry.setdefault("timestamp", time.time())
    try:
        _ledger.insert_one(dict(entry))
    except Exception:
        return
    # soft cap — keep last N
    total = _ledger.estimated_document_count()
    if total > LEDGER_SOFT_CAP + 500:
        overflow = total - LEDGER_SOFT_CAP
        cursor = _ledger.find({}, {"_id": 1}).sort("timestamp", 1).limit(overflow)
        ids = [d["_id"] for d in cursor]
        if ids:
            _ledger.delete_many({"_id": {"$in": ids}})


def log_many(entries: list[dict]) -> int:
    if not entries:
        return 0
    now = time.time()
    for e in entries:
        e.setdefault("timestamp", now)
    _ledger.insert_many([dict(e) for e in entries], ordered=False)
    return len(entries)


def notebook(agent_code: str, limit: int = 20) -> list[dict]:
    out = []
    for d in _ledger.find({"agent_code": agent_code}).sort("timestamp", -1).limit(limit):
        d.pop("_id", None)
        out.append(d)
    return out


def stats(top: int = 10) -> dict:
    total = _ledger.estimated_document_count()
    pipeline = [
        {"$group": {"_id": "$agent_code", "contributions": {"$sum": 1},
                    "influence": {"$sum": "$influence_score"},
                    "last": {"$max": "$timestamp"},
                    "agent": {"$first": "$speaker_agent"}}},
        {"$sort": {"influence": -1}},
        {"$limit": max(1, top)},
    ]
    try:
        top_talkers = list(_ledger.aggregate(pipeline))
    except Exception:
        top_talkers = []
    return {
        "total_entries": total,
        "soft_cap": LEDGER_SOFT_CAP,
        "top_talkers": [
            {"agent_code": t["_id"], "agent": t.get("agent"),
             "contributions": t["contributions"], "influence": t["influence"]}
            for t in top_talkers
        ],
    }


def contributions_for_build(build_id: str, limit: int = 200) -> list[dict]:
    out = []
    for d in _ledger.find({"build_id": build_id}).sort("timestamp", -1).limit(limit):
        d.pop("_id", None)
        out.append(d)
    return out
