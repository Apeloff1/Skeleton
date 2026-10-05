"""
CHAT VAULT — Persistent MongoDB logging for all chat rooms.
Every message, response, and interaction is stored permanently.
Full audit trail, searchable history, and analytics.
"""

import os
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
# ★ Consolidated 2026-02 — shared MongoDB client (lazy connect, fast timeouts)
from core.databases import client as _SHARED_MONGO_CLIENT
from dotenv import load_dotenv

load_dotenv()

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")

# MongoDB connection
_client = _SHARED_MONGO_CLIENT  # consolidated → core.databases.client
_db = _client["tutolage"]


# =============================================================================
# COLLECTIONS
# =============================================================================

chat_vault = _db["chat_vault"]            # All chat messages
vault_sessions = _db["vault_sessions"]     # Session tracking
vault_analytics = _db["vault_analytics"]   # Aggregated analytics


# =============================================================================
# VAULT LOGGING FUNCTIONS
# =============================================================================

async def log_chat_message(
    room_id: str,
    agent_id: str,
    agent_name: str,
    agent_role: str,
    category: str,
    user_message: str,
    agent_response: str,
    session_id: str = "default",
    game_context: str = "",
    success: bool = True,
    metadata: dict = None,
) -> str:
    """Log a chat message to the vault. Returns the vault entry ID."""
    entry = {
        "room_id": room_id,
        "agent_id": agent_id,
        "agent_name": agent_name,
        "agent_role": agent_role,
        "category": category,
        "user_message": user_message,
        "agent_response": agent_response,
        "session_id": session_id,
        "game_context": game_context,
        "success": success,
        "metadata": metadata or {},
        "timestamp": datetime.utcnow(),
        "logged_at": datetime.utcnow().isoformat(),
    }
    result = await chat_vault.insert_one(entry)
    return str(result.inserted_id)


async def log_shadow_review(
    original_agent_id: str,
    shadow_agent_id: str,
    original_output: str,
    shadow_review: str,
    verdict: str,
    session_id: str = "default",
    game_context: str = "",
) -> str:
    """Log a shadow review to the vault."""
    entry = {
        "room_id": "shadow_review",
        "agent_id": shadow_agent_id,
        "original_agent_id": original_agent_id,
        "agent_name": f"Shadow Review",
        "agent_role": "SOTA Quality Review",
        "category": "parallel_society",
        "user_message": original_output,
        "agent_response": shadow_review,
        "session_id": session_id,
        "game_context": game_context,
        "verdict": verdict,
        "success": True,
        "metadata": {"type": "shadow_review", "verdict": verdict},
        "timestamp": datetime.utcnow(),
        "logged_at": datetime.utcnow().isoformat(),
    }
    result = await chat_vault.insert_one(entry)
    return str(result.inserted_id)


# =============================================================================
# VAULT QUERY FUNCTIONS
# =============================================================================

async def get_room_history(room_id: str, limit: int = 50, skip: int = 0) -> list:
    """Get chat history for a specific room."""
    cursor = chat_vault.find(
        {"room_id": room_id},
        {"_id": 0}
    ).sort("timestamp", -1).skip(skip).limit(limit)
    return await cursor.to_list(length=limit)


async def get_agent_log(agent_id: str, limit: int = 50, skip: int = 0) -> list:
    """Get all chat history for a specific agent."""
    cursor = chat_vault.find(
        {"agent_id": agent_id},
        {"_id": 0}
    ).sort("timestamp", -1).skip(skip).limit(limit)
    return await cursor.to_list(length=limit)


async def get_session_history(session_id: str, limit: int = 100) -> list:
    """Get all chat history for a specific session."""
    cursor = chat_vault.find(
        {"session_id": session_id},
        {"_id": 0}
    ).sort("timestamp", 1).limit(limit)
    return await cursor.to_list(length=limit)


async def search_vault(query: str, limit: int = 50) -> list:
    """Search vault messages by text content."""
    cursor = chat_vault.find(
        {"$or": [
            {"user_message": {"$regex": query, "$options": "i"}},
            {"agent_response": {"$regex": query, "$options": "i"}},
            {"agent_name": {"$regex": query, "$options": "i"}},
        ]},
        {"_id": 0}
    ).sort("timestamp", -1).limit(limit)
    return await cursor.to_list(length=limit)


async def get_vault_stats() -> dict:
    """Get vault statistics."""
    total_messages = await chat_vault.count_documents({})
    total_rooms = len(await chat_vault.distinct("room_id"))
    total_agents = len(await chat_vault.distinct("agent_id"))
    total_sessions = len(await chat_vault.distinct("session_id"))
    shadow_reviews = await chat_vault.count_documents({"metadata.type": "shadow_review"})

    # Recent activity (last 24 hours)
    from datetime import timedelta
    day_ago = datetime.utcnow() - timedelta(hours=24)
    recent_messages = await chat_vault.count_documents({"timestamp": {"$gte": day_ago}})

    # Top active rooms
    pipeline = [
        {"$group": {"_id": "$room_id", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]
    top_rooms = await chat_vault.aggregate(pipeline).to_list(length=10)

    # Top active agents
    pipeline_agents = [
        {"$group": {"_id": "$agent_id", "name": {"$first": "$agent_name"}, "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]
    top_agents = await chat_vault.aggregate(pipeline_agents).to_list(length=10)

    return {
        "total_messages": total_messages,
        "total_rooms_active": total_rooms,
        "total_agents_active": total_agents,
        "total_sessions": total_sessions,
        "shadow_reviews": shadow_reviews,
        "messages_last_24h": recent_messages,
        "top_rooms": [{"room_id": r["_id"], "messages": r["count"]} for r in top_rooms],
        "top_agents": [{"agent_id": a["_id"], "name": a.get("name", ""), "messages": a["count"]} for a in top_agents],
        "vault_status": "ONLINE",
        "persistence": "MongoDB",
    }


# =============================================================================
# ENSURE INDEXES
# =============================================================================

async def ensure_vault_indexes():
    """Create indexes for efficient vault queries."""
    await chat_vault.create_index("room_id")
    await chat_vault.create_index("agent_id")
    await chat_vault.create_index("session_id")
    await chat_vault.create_index("timestamp")
    await chat_vault.create_index([("user_message", "text"), ("agent_response", "text")])
