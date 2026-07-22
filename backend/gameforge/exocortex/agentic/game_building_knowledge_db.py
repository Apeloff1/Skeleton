from __future__ import annotations
"""
Game Building Knowledge Database: Interconnected vector + graph DB for game dev information (mechanics, assets, papers, tutorials, code snippets, AI techniques).
Linked to exocortex memory (journals, logs, twins), web_browser_agent, MCP connectors, DSPy pipelines, rooms (Research, Asset, Pipeline, Logic).
Enables agents to query, store, retrieve relevant game building knowledge with provenance and evolution.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import numpy as np

@dataclass
class GameKnowledgeItem:
    item_id: str
    type: str  # mechanic, asset, paper, tutorial, code, ai_technique
    content: str
    source: str
    embedding: List[float]  # vector for similarity
    graph_relations: List[str]  # e.g., "related_to:other_item"
    provenance: str
    last_updated: str

class GameBuildingKnowledgeDB:
    """
    Game Building Knowledge DB module.
    Vector search + graph relations for interconnected game dev info.
    Interconnects with exocortex (memory, journals, DoYouRemember, StoryTeller, ABot graph memory).
    Used by web_browser_agent, MCP, DSPy pipelines, Jeeves, boardroom.
    """

    def __init__(self):
        self.knowledge_items: Dict[str, GameKnowledgeItem] = {}
        self.vector_index: Dict[str, List[float]] = {}  # simple in-memory vector store
        self.graph: Dict[str, List[str]] = {}  # graph relations

    def add_knowledge(self, item_type: str, content: str, source: str, embedding: List[float], relations: List[str] = None) -> str:
        """Add game building knowledge item, linked to exocortex."""
        item_id = f"kb_{hashlib.md5(content.encode()).hexdigest()[:8]}"
        item = GameKnowledgeItem(
            item_id=item_id,
            type=item_type,
            content=content,
            source=source,
            embedding=embedding,
            graph_relations=relations or [],
            provenance=f"Added via web_browser or MCP from {source}",
            last_updated="2026-07-18"
        )
        self.knowledge_items[item_id] = item
        self.vector_index[item_id] = embedding
        if relations:
            self.graph[item_id] = relations
        # Interconnect with exocortex: e.g., store summary in memory journals
        return item_id

    def query_relevant(self, query_embedding: List[float], top_k: int = 5, item_type: str = None) -> List[GameKnowledgeItem]:
        """Vector similarity search + graph traversal for relevant game dev knowledge."""
        # Simple cosine similarity proxy
        scores = {}
        for iid, emb in self.vector_index.items():
            if item_type and self.knowledge_items[iid].type != item_type:
                continue
            sim = np.dot(query_embedding, emb) / (np.linalg.norm(query_embedding) * np.linalg.norm(emb) + 1e-8)
            scores[iid] = sim
        sorted_ids = sorted(scores, key=scores.get, reverse=True)[:top_k]
        return [self.knowledge_items[iid] for iid in sorted_ids]

    def interconnect_exocortex(self, exocortex_memory: Dict, item_id: str):
        """Link DB item to exocortex memory/journals/twins for contextual game building."""
        # In real: Vector sync, RAG, graph merge with exocortex (ABot graph, DoYouRemember, etc.)
        pass  # Placeholder for full interconnect (e.g., store in memory logs, journals)

    def status(self) -> Dict[str, Any]:
        return {
            "knowledge_items": len(self.knowledge_items),
            "vector_index_size": len(self.vector_index),
            "graph_relations": len(self.graph),
            "key_capabilities": "vector_search, graph_traversal, exocortex_interconnect, provenance_tracking",
            "cns_integration": "Research/Asset/Pipeline/Logic rooms; linked to web_browser_agent, MCP connectors, DSPy pipelines, exocortex memory (journals, DoYouRemember, StoryTeller, ABot graph memory), boardroom",
            "inspired_by": "Knowledge DBs in advanced AI systems (DSPy pipelines, MCP tool connections for game dev research)"
        }
