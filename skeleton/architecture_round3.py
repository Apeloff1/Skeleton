"""
Skeleton — Round-3 architecture addendum

Registers the modules added in the retrieval/intelligence/gameforge
hardening rounds so `skeleton.architecture` stays accurate.
"""

from __future__ import annotations

from typing import Any, Dict

from skeleton import architecture as base


NEW_MODULES: Dict[str, Dict[str, Any]] = {
    "skeleton.memory.vector": {
        "layer": "memory",
        "purpose": "Dense embedding retrieval (HashEmbedder + VectorStore, cosine similarity)",
        "exports": ["VectorStore", "HashEmbedder", "VectorEntry"],
    },
    "skeleton.retrieval.kag": {
        "layer": "retrieval",
        "purpose": "KAG plane: typed knowledge graph with traversal retrieval",
        "exports": ["KnowledgeGraph", "KAGRetriever", "Triple"],
    },
    "skeleton.retrieval.ranking": {
        "layer": "retrieval",
        "purpose": "Blended score ranking with recency + diversity",
        "exports": ["Ranker"],
    },
    "skeleton.jeeves.providers": {
        "layer": "jeeves",
        "purpose": "LLM provider abstraction: local-echo fallback, OpenAI, Anthropic",
        "exports": ["LLMProvider", "LocalEchoProvider", "OpenAIProvider", "AnthropicProvider", "get_provider"],
    },
    "skeleton.cortex.live": {
        "layer": "cortex",
        "purpose": "Process-lived serving singleton for the JeevesCortex",
        "exports": ["get_live", "get_control", "attach", "status"],
    },
    "skeleton.pipelines.gameforge": {
        "layer": "pipelines",
        "purpose": "End-to-end game generation: intake → blueprint → materialise → NPC/logic/animation",
        "exports": ["GameForge", "GameSpec"],
    },
    "skeleton.api.gameforge_routes": {
        "layer": "api",
        "purpose": "GameForge REST routes (/gameforge/run, /gameforge/intake) with HMAC + idempotency",
        "exports": ["router"],
    },
    "skeleton.intelligence.dream": {
        "layer": "memory",
        "purpose": "DreamEngine: MAG episode clustering into thematic RAG documents",
        "exports": ["DreamEngine"],
    },
}

NEW_ROUTES = [
    {"method": "POST", "path": "/api/v1/gameforge/intake", "protected": False},
    {"method": "POST", "path": "/api/v1/gameforge/run", "protected": True},
    {"method": "GET", "path": "/cortex/status", "protected": False},
]


def summary() -> Dict[str, Any]:
    base_summary = base.architecture_summary()
    return {
        **base_summary,
        "round3_modules": len(NEW_MODULES),
        "round3_routes": len(NEW_ROUTES),
        "retrieval_planes": ["rag (vector)", "cag", "mag", "kag"],
        "llm_providers": ["local-echo", "openai", "anthropic"],
    }
