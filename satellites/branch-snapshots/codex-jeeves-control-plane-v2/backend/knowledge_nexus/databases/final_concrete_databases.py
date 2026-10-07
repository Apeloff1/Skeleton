#!/usr/bin/env python3
"""
Final Concrete Database Implementations
Completing the expanded database set.
"""

from databases.database_abstraction_layer import BaseDatabase, DBRecord
from typing import Dict, Any, List
import time

class FineDetailStickyNotesDB(BaseDatabase):
    def __init__(self):
        super().__init__("Fine Detail StickyNotes DB")
        self.stickynotes = []

    def store(self, record_id: str, content: Any, metadata: Dict = None):
        note = {
            "id": record_id,
            "content": content,
            "metadata": metadata or {},
            "timestamp": time.time(),
            "tags": metadata.get("tags", []) if metadata else []
        }
        self.records[record_id] = DBRecord(**note)
        self.stickynotes.append(note)

    def get_by_tag(self, tag: str) -> List[Dict]:
        return [note for note in self.stickynotes if tag in note.get("tags", [])]

    def retrieve(self, record_id: str):
        return self.records.get(record_id)

class PriorityQuadJournalsDB(BaseDatabase):
    def __init__(self):
        super().__init__("Priority & Quad Journals DB")
        self.journals = {"high": [], "medium": [], "low": [], "backlog": []}

    def store(self, record_id: str, content: Any, metadata: Dict = None):
        priority = metadata.get("priority", "medium") if metadata else "medium"
        if priority in self.journals:
            self.journals[priority].append({
                "id": record_id,
                "content": content,
                "timestamp": time.time()
            })
        self.records[record_id] = DBRecord(id=record_id, content=content, metadata=metadata or {}, timestamp=time.time())

    def get_by_priority(self, priority: str):
        return self.journals.get(priority, [])

    def retrieve(self, record_id: str):
        return self.records.get(record_id)

class MainMemoryIndexDB(BaseDatabase):
    def __init__(self):
        super().__init__("Main Memory Index DB")
        self.index = {}

    def store(self, record_id: str, content: Any, metadata: Dict = None):
        self.records[record_id] = DBRecord(id=record_id, content=content, metadata=metadata or {}, timestamp=time.time())
        self.index[record_id] = {
            "content_preview": str(content)[:100],
            "metadata": metadata or {},
            "timestamp": time.time()
        }

    def unified_search(self, query: str, top_k: int = 20):
        # This would normally call AAAHRAG/Hybrid RAG across all DBs
        results = []
        for rid, data in self.index.items():
            if query.lower() in data["content_preview"].lower():
                results.append({"id": rid, **data})
        return results[:top_k]

    def retrieve(self, record_id: str):
        return self.records.get(record_id)

# Instances
stickynotes_db = FineDetailStickyNotesDB()
priority_journals_db = PriorityQuadJournalsDB()
main_memory_index_db = MainMemoryIndexDB()