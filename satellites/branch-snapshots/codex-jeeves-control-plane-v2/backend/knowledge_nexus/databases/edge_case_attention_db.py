#!/usr/bin/env python3
"""
Edge Case Database + Attention Memory DB implementations.
"""

from databases.database_abstraction_layer import BaseDatabase, DBRecord
import time
from typing import Dict, Any, List

class EdgeCaseDatabase(BaseDatabase):
    def __init__(self):
        super().__init__("Edge Case Database")
        self.edge_cases = []

    def store(self, record_id: str, content: Any, metadata: Dict = None):
        entry = {
            "id": record_id,
            "content": content,
            "metadata": metadata or {},
            "timestamp": time.time(),
            "resolved": False
        }
        self.records[record_id] = DBRecord(**entry)
        self.edge_cases.append(entry)

    def get_unresolved(self) -> List[Dict]:
        return [e for e in self.edge_cases if not e.get("resolved")]

    def retrieve(self, record_id: str):
        return self.records.get(record_id)

class AttentionMemoryDB(BaseDatabase):
    def __init__(self):
        super().__init__("Attention Memory DB")
        self.attention_items = []

    def store(self, record_id: str, content: Any, metadata: Dict = None):
        item = {
            "id": record_id,
            "content": content,
            "attention_score": metadata.get("attention_score", 0.5) if metadata else 0.5,
            "timestamp": time.time()
        }
        self.records[record_id] = DBRecord(**item)
        self.attention_items.append(item)

    def get_high_attention(self, threshold: float = 0.7) -> List[Dict]:
        return [item for item in self.attention_items if item["attention_score"] >= threshold]

    def retrieve(self, record_id: str):
        return self.records.get(record_id)

# Instances
edge_case_db = EdgeCaseDatabase()
attention_memory_db = AttentionMemoryDB()