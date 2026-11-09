#!/usr/bin/env python3
"""
More Concrete Database Implementations
Additional specialized databases from the expanded set.
"""

from databases.database_abstraction_layer import BaseDatabase, DBRecord
from typing import Dict, Any, List
import time

class ItineraryPlanningDB(BaseDatabase):
    def __init__(self):
        super().__init__("Itinerary & Planning DB")
        self.plans = {}

    def store(self, record_id: str, content: Any, metadata: Dict = None):
        self.records[record_id] = DBRecord(
            id=record_id, 
            content=content, 
            metadata=metadata or {}, 
            timestamp=time.time()
        )
        if isinstance(content, dict) and "plan_name" in content:
            self.plans[content["plan_name"]] = content

    def get_active_plans(self) -> List[Dict]:
        return [v for v in self.plans.values() if v.get("status") == "active"]

    def retrieve(self, record_id: str):
        return self.records.get(record_id)

class IntelligentRollodexDB(BaseDatabase):
    def __init__(self):
        super().__init__("Intelligent Rollodex DB")
        self.contacts = {}

    def store(self, record_id: str, content: Any, metadata: Dict = None):
        self.records[record_id] = DBRecord(id=record_id, content=content, metadata=metadata or {}, timestamp=time.time())
        if isinstance(content, dict) and "entity_name" in content:
            self.contacts[content["entity_name"]] = content

    def find_by_entity(self, entity_name: str):
        return self.contacts.get(entity_name)

    def retrieve(self, record_id: str):
        return self.records.get(record_id)

class QuadNoteblockDB(BaseDatabase):
    def __init__(self):
        super().__init__("Quad Noteblock DB")
        self.layers = {"layer_1": [], "layer_2": [], "layer_3": [], "layer_4": []}

    def store(self, record_id: str, content: Any, metadata: Dict = None):
        layer = metadata.get("layer", "layer_1") if metadata else "layer_1"
        if layer in self.layers:
            self.layers[layer].append({"id": record_id, "content": content, "timestamp": time.time()})
        self.records[record_id] = DBRecord(id=record_id, content=content, metadata=metadata or {}, timestamp=time.time())

    def get_layer(self, layer: str):
        return self.layers.get(layer, [])

    def retrieve(self, record_id: str):
        return self.records.get(record_id)

class QuadNotebookDB(BaseDatabase):
    def __init__(self):
        super().__init__("Quad Notebook DB")
        self.redundant_copies = {"copy_a": {}, "copy_b": {}, "copy_c": {}, "copy_d": {}}

    def store(self, record_id: str, content: Any, metadata: Dict = None):
        for copy in self.redundant_copies:
            self.redundant_copies[copy][record_id] = {
                "content": content,
                "timestamp": time.time(),
                "metadata": metadata or {}
            }
        self.records[record_id] = DBRecord(id=record_id, content=content, metadata=metadata or {}, timestamp=time.time())

    def retrieve(self, record_id: str, preferred_copy: str = "copy_a"):
        return self.redundant_copies.get(preferred_copy, {}).get(record_id)

# Quick access instances
itinerary_db = ItineraryPlanningDB()
rollodex_db = IntelligentRollodexDB()
quad_noteblock_db = QuadNoteblockDB()
quad_notebook_db = QuadNotebookDB()