#!/usr/bin/env python3
"""
Wiki Memory Engine
Handles build-wiki, sync-wiki, diff calculation, and Knowledge Graph updates.
"""

from typing import Dict, List, Any
import time
from dataclasses import dataclass

@dataclass
class WikiEntry:
    id: str
    content: str
    sources: List[str]
    entities: List[str]
    last_updated: float
    provenance: Dict[str, Any]

class WikiMemoryEngine:
    def __init__(self):
        self.wiki_entries: Dict[str, WikiEntry] = {}
        self.knowledge_graph = {}  # Simple graph: entity -> connected entities
        self.raw_cache = {}

    def build_wiki(self, content_id: str, content: str, 
                   sources: List[str] = None, entities: List[str] = None) -> WikiEntry:
        """Create or update a Wiki entry."""
        entry = WikiEntry(
            id=content_id,
            content=content,
            sources=sources or [],
            entities=entities or [],
            last_updated=time.time(),
            provenance={"approved_by": "Knowledge_Nexus_Jury", "timestamp": time.time()}
        )
        self.wiki_entries[content_id] = entry
        
        # Update Knowledge Graph
        for entity in entry.entities:
            if entity not in self.knowledge_graph:
                self.knowledge_graph[entity] = set()
            for other in entry.entities:
                if other != entity:
                    self.knowledge_graph[entity].add(other)
        
        return entry

    def sync_wiki(self, content_id: str, new_content: str) -> Dict:
        """Sync changes and calculate diff."""
        if content_id not in self.wiki_entries:
            return {"status": "created", "entry": self.build_wiki(content_id, new_content)}
        
        old_entry = self.wiki_entries[content_id]
        diff = {
            "old": old_entry.content[:200] + "...",
            "new": new_content[:200] + "...",
            "changed": old_entry.content != new_content
        }
        
        if diff["changed"]:
            old_entry.content = new_content
            old_entry.last_updated = time.time()
        
        return {"status": "synced", "diff": diff, "entry": old_entry}

    def get_wiki_context(self, query: str, top_k: int = 5) -> List[WikiEntry]:
        """Simple retrieval from Wiki Memory (real version would use AAAHRAG)."""
        results = []
        for entry in self.wiki_entries.values():
            if query.lower() in entry.content.lower():
                results.append(entry)
        return results[:top_k]

# Global instance
wiki_memory_engine = WikiMemoryEngine()