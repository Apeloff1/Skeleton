#!/usr/bin/env python3
"""
Fog of Knowledge System
Partial observability for the Nav Map and RAG. Agents only see what they have earned visibility for.
"""

from typing import Dict
from datetime import datetime

class FogOfKnowledgeSystem:
    def __init__(self):
        self.node_visibility = {}  # node_id -> visibility level

    def get_visibility(self, node_id: str) -> str:
        return self.node_visibility.get(node_id, "Unknown")

    def reveal_node(self, node_id: str, level: str = "Partially Known"):
        """Increase visibility of a node."""
        current = self.node_visibility.get(node_id, "Unknown")
        levels = ["Unknown", "Partially Known", "Known", "Fully Known"]
        
        if levels.index(level) > levels.index(current):
            self.node_visibility[node_id] = level

        return {
            "node": node_id,
            "new_visibility": level,
            "timestamp": datetime.now().isoformat()
        }

    def can_access_details(self, node_id: str) -> bool:
        """Check if agent has enough visibility for detailed information."""
        visibility = self.get_visibility(node_id)
        return visibility in ["Known", "Fully Known"]

if __name__ == "__main__":
    fog = FogOfKnowledgeSystem()
    print("Fog of Knowledge System ready. Partial observability active.")
