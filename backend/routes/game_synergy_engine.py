"""
SYNERGY ENGINE — Cross-Agent Intelligence & Vault Integration
Ensures all 25,994 agents, the vault system, and Jeeves orchestrator work in harmony.

SYNERGY GAPS IDENTIFIED & FIXED:
1. Layer-specific vault logging (ghost/angel/seraphim/cherubim reviews were untracked)
2. Jeeves learning loop — consumes vault data to improve orchestration
3. Cross-agent synergy tracking — measures how agents enhance each other
4. Vault enrichment — layer-specific analytics and cross-reference scoring
5. Wisdom synthesis — Jeeves distills vault knowledge into actionable insights

Philosophy: "A symphony is not 100 instruments playing separately —
it is 100 instruments playing AS ONE. Synergy is not addition; it is multiplication."
"""

from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
# ★ Consolidated 2026-02 — shared MongoDB client (lazy connect, fast timeouts)
from core.databases import client as _SHARED_MONGO_CLIENT
import os
from dotenv import load_dotenv

load_dotenv()

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
_client = _SHARED_MONGO_CLIENT  # consolidated → core.databases.client
_db = _client["tutolage"]

# Collections
chat_vault = _db["chat_vault"]
synergy_log = _db["synergy_log"]
jeeves_wisdom = _db["jeeves_wisdom"]
code_vault = _db["code_vault"]


# =============================================================================
# LAYER-SPECIFIC VAULT LOGGING
# =============================================================================

async def log_ghost_review(
    original_agent_id: str, ghost_agent_id: str,
    original_output: str, ghost_review: str,
    methodology_focus: str, verdict: str = "PENDING",
    session_id: str = "default", game_context: str = "",
) -> str:
    """Log a ghost methodology review to the vault with full traceability."""
    entry = {
        "room_id": "ghost_review",
        "agent_id": ghost_agent_id,
        "original_agent_id": original_agent_id,
        "agent_name": "Ghost Review",
        "agent_role": "Methodology Enforcement",
        "category": "ghost_society",
        "layer": "ghost",
        "user_message": original_output,
        "agent_response": ghost_review,
        "methodology_focus": methodology_focus,
        "session_id": session_id,
        "game_context": game_context,
        "verdict": verdict,
        "success": True,
        "metadata": {"type": "ghost_review", "verdict": verdict, "methodology_focus": methodology_focus},
        "timestamp": datetime.utcnow(),
        "logged_at": datetime.utcnow().isoformat(),
        "synergy_tracked": True,
    }
    result = await chat_vault.insert_one(entry)

    # Track synergy
    await _track_synergy_event("ghost_review", original_agent_id, ghost_agent_id, session_id)

    return str(result.inserted_id)


async def log_angel_review(
    target_agent_id: str, angel_agent_id: str,
    target_output: str, angel_review: str,
    complexity_focus: str, layer: str = "original",
    verdict: str = "PENDING", session_id: str = "default", game_context: str = "",
) -> str:
    """Log an angel complexity review to the vault."""
    entry = {
        "room_id": "angel_review",
        "agent_id": angel_agent_id,
        "original_agent_id": target_agent_id,
        "agent_name": "Angel Review",
        "agent_role": "Complexity Guardian",
        "category": "angel_class",
        "layer": "angel",
        "target_layer": layer,
        "user_message": target_output,
        "agent_response": angel_review,
        "complexity_focus": complexity_focus,
        "session_id": session_id,
        "game_context": game_context,
        "verdict": verdict,
        "success": True,
        "metadata": {"type": "angel_review", "verdict": verdict, "complexity_focus": complexity_focus, "target_layer": layer},
        "timestamp": datetime.utcnow(),
        "logged_at": datetime.utcnow().isoformat(),
        "synergy_tracked": True,
    }
    result = await chat_vault.insert_one(entry)
    await _track_synergy_event("angel_review", target_agent_id, angel_agent_id, session_id)
    return str(result.inserted_id)


async def log_seraphim_review(
    angel_agent_id: str, seraphim_agent_id: str,
    angel_output: str, seraphim_review: str,
    intricacy_focus: str, verdict: str = "PENDING",
    session_id: str = "default", game_context: str = "",
) -> str:
    """Log a seraphim intricacy review to the vault."""
    entry = {
        "room_id": "seraphim_review",
        "agent_id": seraphim_agent_id,
        "original_agent_id": angel_agent_id,
        "agent_name": "Seraphim Review",
        "agent_role": "Intricacy Arbiter",
        "category": "seraphim_class",
        "layer": "seraphim",
        "user_message": angel_output,
        "agent_response": seraphim_review,
        "intricacy_focus": intricacy_focus,
        "session_id": session_id,
        "game_context": game_context,
        "verdict": verdict,
        "success": True,
        "metadata": {"type": "seraphim_review", "verdict": verdict, "intricacy_focus": intricacy_focus},
        "timestamp": datetime.utcnow(),
        "logged_at": datetime.utcnow().isoformat(),
        "synergy_tracked": True,
    }
    result = await chat_vault.insert_one(entry)
    await _track_synergy_event("seraphim_review", angel_agent_id, seraphim_agent_id, session_id)
    return str(result.inserted_id)


async def log_cherubim_review(
    target_agent_id: str, cherubim_agent_id: str,
    target_output: str, cherubim_review: str,
    diligence_focus: str, source_layer: str = "original",
    verdict: str = "PENDING", session_id: str = "default", game_context: str = "",
) -> str:
    """Log a cherubim diligence review to the vault."""
    entry = {
        "room_id": "cherubim_review",
        "agent_id": cherubim_agent_id,
        "original_agent_id": target_agent_id,
        "agent_name": "Cherubim Review",
        "agent_role": "Diligence Enforcer",
        "category": "cherubim_class",
        "layer": "cherubim",
        "source_layer": source_layer,
        "user_message": target_output,
        "agent_response": cherubim_review,
        "diligence_focus": diligence_focus,
        "session_id": session_id,
        "game_context": game_context,
        "verdict": verdict,
        "success": True,
        "metadata": {"type": "cherubim_review", "verdict": verdict, "diligence_focus": diligence_focus, "source_layer": source_layer},
        "timestamp": datetime.utcnow(),
        "logged_at": datetime.utcnow().isoformat(),
        "synergy_tracked": True,
    }
    result = await chat_vault.insert_one(entry)
    await _track_synergy_event("cherubim_review", target_agent_id, cherubim_agent_id, session_id)
    return str(result.inserted_id)


# =============================================================================
# CROSS-AGENT SYNERGY TRACKING
# =============================================================================

async def _track_synergy_event(event_type: str, source_agent: str, target_agent: str, session_id: str):
    """Track a synergy event between two agents."""
    await synergy_log.insert_one({
        "event_type": event_type,
        "source_agent": source_agent,
        "target_agent": target_agent,
        "session_id": session_id,
        "timestamp": datetime.utcnow(),
    })


async def get_synergy_stats() -> dict:
    """Get comprehensive synergy statistics across all layers."""
    total_events = await synergy_log.count_documents({})

    # Events by type
    pipeline_by_type = [
        {"$group": {"_id": "$event_type", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    by_type = await synergy_log.aggregate(pipeline_by_type).to_list(20)

    # Vault stats by layer
    layer_stats = {}
    for layer in ["shadow_review", "ghost_review", "angel_review", "seraphim_review", "cherubim_review"]:
        count = await chat_vault.count_documents({"metadata.type": layer})
        layer_stats[layer] = count

    # Total vault entries
    total_vault = await chat_vault.count_documents({})
    total_code_vault = await code_vault.count_documents({})

    # Jeeves wisdom entries
    total_wisdom = await jeeves_wisdom.count_documents({})

    # Recent activity (24h)
    day_ago = datetime.utcnow() - timedelta(hours=24)
    recent_events = await synergy_log.count_documents({"timestamp": {"$gte": day_ago}})
    recent_vault = await chat_vault.count_documents({"timestamp": {"$gte": day_ago}})

    # Most active agent pairs
    pair_pipeline = [
        {"$group": {"_id": {"source": "$source_agent", "target": "$target_agent"}, "interactions": {"$sum": 1}}},
        {"$sort": {"interactions": -1}},
        {"$limit": 10},
    ]
    top_pairs = await synergy_log.aggregate(pair_pipeline).to_list(10)

    return {
        "synergy_events": {
            "total": total_events,
            "by_type": {e["_id"]: e["count"] for e in by_type},
            "recent_24h": recent_events,
        },
        "vault_coverage": {
            "chat_vault_entries": total_vault,
            "code_vault_entries": total_code_vault,
            "layer_reviews": layer_stats,
            "recent_24h": recent_vault,
        },
        "jeeves_wisdom": {
            "total_insights": total_wisdom,
        },
        "top_agent_pairs": [
            {"source": p["_id"]["source"], "target": p["_id"]["target"], "interactions": p["interactions"]}
            for p in top_pairs
        ],
        "synergy_health": "OPTIMAL" if total_vault > 0 else "INITIALIZING",
    }


# =============================================================================
# JEEVES LEARNING LOOP
# =============================================================================

async def jeeves_learn_from_vault(project_id: str = None, limit: int = 100) -> dict:
    """Jeeves consumes vault data to build cumulative wisdom.
    Scans unlearned vault entries, extracts patterns, and stores insights."""

    # Find unlearned entries
    query = {"learned_by_jeeves": False}
    if project_id:
        query["metadata.project_id"] = project_id

    unlearned = await code_vault.find(query).sort("stored_at", -1).limit(limit).to_list(limit)

    if not unlearned:
        return {"status": "nothing_new", "message": "Jeeves is up to date — no new vault entries to learn from."}

    learned_count = 0
    insights = []

    for entry in unlearned:
        agent_id = entry.get("agent_id", "unknown")
        agent_name = entry.get("agent_name", "Unknown")
        content_type = entry.get("content_type", "unknown")
        content = entry.get("content", "")
        code_blocks = entry.get("code_blocks", [])

        # Extract insight
        insight = {
            "source_agent": agent_id,
            "source_agent_name": agent_name,
            "content_type": content_type,
            "project_id": entry.get("metadata", {}).get("project_id"),
            "key_takeaway": content[:500] if content else "No content",
            "code_blocks_count": len(code_blocks),
            "has_code": len(code_blocks) > 0,
            "learned_at": datetime.utcnow().isoformat(),
            "applied_to_future_builds": False,
        }
        insights.append(insight)

        # Mark as learned
        entry_id = entry.get("_id")
        if entry_id:
            await code_vault.update_one({"_id": entry_id}, {"$set": {"learned_by_jeeves": True}})
            learned_count += 1

    # Store insights in jeeves_wisdom
    if insights:
        await jeeves_wisdom.insert_many([{
            **insight,
            "wisdom_type": "vault_learning",
            "timestamp": datetime.utcnow(),
        } for insight in insights])

    return {
        "status": "learned",
        "entries_processed": learned_count,
        "insights_generated": len(insights),
        "content_types_learned": list(set(i["content_type"] for i in insights)),
        "agents_learned_from": list(set(i["source_agent_name"] for i in insights)),
        "message": f"Jeeves absorbed {learned_count} vault entries and generated {len(insights)} insights.",
    }


async def jeeves_get_wisdom(project_id: str = None, limit: int = 50) -> dict:
    """Get Jeeves' accumulated wisdom — synthesized from all vault data."""
    query = {}
    if project_id:
        query["project_id"] = project_id

    wisdom_entries = await jeeves_wisdom.find(query).sort("timestamp", -1).limit(limit).to_list(limit)
    for w in wisdom_entries:
        w.pop("_id", None)

    total_wisdom = await jeeves_wisdom.count_documents(query)

    # Aggregate by content type
    type_pipeline = [
        {"$group": {"_id": "$content_type", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    by_type = await jeeves_wisdom.aggregate(type_pipeline).to_list(50)

    # Aggregate by source agent
    agent_pipeline = [
        {"$group": {"_id": "$source_agent_name", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 20},
    ]
    by_agent = await jeeves_wisdom.aggregate(agent_pipeline).to_list(20)

    return {
        "total_wisdom_entries": total_wisdom,
        "recent_insights": wisdom_entries[:10],
        "by_content_type": {t["_id"]: t["count"] for t in by_type},
        "by_source_agent": {a["_id"]: a["count"] for a in by_agent},
        "jeeves_status": "OMNISCIENT" if total_wisdom > 50 else "LEARNING" if total_wisdom > 0 else "AWAITING_DATA",
        "philosophy": "I learn from every agent so I can orchestrate them all. The more they teach me, the better I serve.",
    }


# =============================================================================
# VAULT ENRICHMENT — Cross-Layer Analytics
# =============================================================================

async def get_enriched_vault_stats() -> dict:
    """Enhanced vault statistics with full layer coverage and synergy metrics."""
    base_stats = {}

    # Total by category
    cat_pipeline = [
        {"$group": {"_id": "$category", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    by_category = await chat_vault.aggregate(cat_pipeline).to_list(50)

    # Layer-specific review counts
    review_types = {
        "shadow_review": await chat_vault.count_documents({"metadata.type": "shadow_review"}),
        "ghost_review": await chat_vault.count_documents({"metadata.type": "ghost_review"}),
        "angel_review": await chat_vault.count_documents({"metadata.type": "angel_review"}),
        "seraphim_review": await chat_vault.count_documents({"metadata.type": "seraphim_review"}),
        "cherubim_review": await chat_vault.count_documents({"metadata.type": "cherubim_review"}),
    }

    # Code vault stats
    code_total = await code_vault.count_documents({})
    code_parsed = await code_vault.count_documents({"parsed_by_jeeves": True})
    code_learned = await code_vault.count_documents({"learned_by_jeeves": True})

    # Verdicts across all reviews
    verdict_pipeline = [
        {"$match": {"metadata.verdict": {"$exists": True}}},
        {"$group": {"_id": "$metadata.verdict", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    verdicts = await chat_vault.aggregate(verdict_pipeline).to_list(20)

    # Synergy score calculation
    total_reviews = sum(review_types.values())
    synergy_score = min(100, total_reviews * 2)  # Simple metric — grows with usage

    return {
        "chat_vault": {
            "total_entries": await chat_vault.count_documents({}),
            "by_category": {c["_id"]: c["count"] for c in by_category},
            "layer_reviews": review_types,
            "total_reviews": total_reviews,
            "verdicts": {v["_id"]: v["count"] for v in verdicts},
        },
        "code_vault": {
            "total_entries": code_total,
            "parsed_by_jeeves": code_parsed,
            "learned_by_jeeves": code_learned,
            "unprocessed": code_total - code_learned,
        },
        "synergy": {
            "score": synergy_score,
            "grade": _synergy_grade(synergy_score),
            "total_cross_layer_reviews": total_reviews,
            "layers_active": sum(1 for v in review_types.values() if v > 0),
            "layers_total": 5,
        },
        "jeeves_integration": {
            "wisdom_entries": await jeeves_wisdom.count_documents({}),
            "vault_coverage_pct": round((code_learned / code_total * 100) if code_total > 0 else 0, 1),
            "status": "FULLY_SYNCED" if code_learned == code_total and code_total > 0 else "SYNCING" if code_learned > 0 else "AWAITING_DATA",
        },
    }


def _synergy_grade(score: int) -> str:
    if score >= 90: return "S+ (Transcendent Harmony)"
    if score >= 75: return "A (Excellent Synergy)"
    if score >= 50: return "B (Good Synergy)"
    if score >= 25: return "C (Building Synergy)"
    return "D (Initializing)"


# =============================================================================
# ENSURE SYNERGY INDEXES
# =============================================================================

async def ensure_synergy_indexes():
    """Create indexes for synergy collections."""
    await synergy_log.create_index("event_type")
    await synergy_log.create_index("source_agent")
    await synergy_log.create_index("target_agent")
    await synergy_log.create_index("timestamp")
    await jeeves_wisdom.create_index("content_type")
    await jeeves_wisdom.create_index("source_agent")
    await jeeves_wisdom.create_index("project_id")
    await jeeves_wisdom.create_index("timestamp")
    # Ensure chat_vault has layer field indexed
    await chat_vault.create_index("layer")
    await chat_vault.create_index("metadata.type")
