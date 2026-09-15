from __future__ import annotations
"""
GameForge CNS - Main Entry Point (S20 / Mobile / Local Deployment)
Zaibatsu-level orchestration of the entire system.
Initializes exocortex, Jeeves, all rooms, Hybrid RAG (sharded), Latent Metrics, MCP, DiP, Grok thinking, queue controls, and room APIs.
"""

import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from gameforge.exocortex.zaibatsu.jeeves_zaibatsu import JeevesZaibatsu
from gameforge.exocortex.agentic.hybrid_rag_engine import HybridRAGEngine
from gameforge.exocortex.agentic.vector_shard_manager import VectorShardManager
from gameforge.exocortex.agentic.latent_metrics_table import LatentMetricsTable
from gameforge.exocortex.agentic.mcp_connectors import MCPConnectors
from gameforge.exocortex.agentic.dspy_game_creation_pipeline import DSPyGameCreationPipeline
from gameforge.exocortex.agentic.grok_thinking import GrokThinkingEngine
from gameforge.rooms.full_room_registry import all_rooms, ensure_room_coherence

def initialize_gameforge_cns(user_id: str = "default") -> dict:
    """
    Zaibatsu-level initialization of the full GameForge CNS.
    Returns the core orchestrator objects ready for use.
    """
    print("[GameForge] Initializing Zaibatsu-level CNS...")

    # Core engines
    jeeves = JeevesZaibatsu(user_id=user_id)
    grok = GrokThinkingEngine()
    rag = HybridRAGEngine(room_id="global")
    shard_manager = VectorShardManager(max_shard_size_mb=40.0)  # S20 safe
    metrics = LatentMetricsTable()
    mcp = MCPConnectors()
    dspy = DSPyGameCreationPipeline()

    # Ensure all 1000 rooms are coherent and have local capabilities
    rooms = all_rooms()
    ensure_room_coherence(rooms)  # This should wire sharded RAG, metrics, MCP, Grok, queue controls per room

    # Inject global instances into Jeeves for app-wide access
    jeeves.hybrid_rag = rag
    jeeves.vector_shards = shard_manager
    jeeves.latent_metrics = metrics
    jeeves.mcp = mcp
    jeeves.dspy = dspy
    jeeves.grok = grok

    print(f"[GameForge] CNS initialized with {len(rooms)} rooms.")
    print("[GameForge] Vector sharding, Hybrid RAG, Latent Metrics, MCP, DiP, Grok thinking, and Room APIs active.")

    return {
        "jeeves": jeeves,
        "hybrid_rag": rag,
        "vector_shards": shard_manager,
        "latent_metrics": metrics,
        "mcp": mcp,
        "dspy": dspy,
        "grok": grok,
        "rooms": rooms,
        "status": "Zaibatsu-level ready for deployment"
    }

if __name__ == "__main__":
    system = initialize_gameforge_cns()
    print("\n[GameForge] System ready. Jeeves queue controls, Grok thinking, and full agentic capabilities available.")
    print("Use jeeves.counsel(), jeeves.start_queue_filling(), etc.")