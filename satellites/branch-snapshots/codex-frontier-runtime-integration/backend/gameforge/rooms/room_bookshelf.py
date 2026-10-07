from __future__ import annotations
from typing import Any, Dict, Optional
from gameforge.roles.role_manager import RoleManager
from gameforge.roles.role_cycling_engine import RoleCyclingEngine

class RoomBookshelf:
    """
    Per-room 'bookshelf' giving agents/teams access to the full 14-type database architecture.
    Acts as the room's cumulated knowledge store.
    Each room has its own isolated bookshelf for persistent knowledge across role cycles and handoffs.
    """

    def __init__(self, room_id: str, room_category: str):
        self.room_id = room_id
        self.room_category = room_category
        self.databases: Dict[str, Any] = {}  # Will hold references to the 14 types
        self._initialize_14_databases()

    def _initialize_14_databases(self):
        """
        Initialize access to all 14 database types, scoped to this room.
        In a full implementation, these would be namespaced partitions or dedicated instances.
        """
        self.databases = {
            "relational": f"room_{self.room_id}_relational",
            "columnar": f"room_{self.room_id}_columnar",
            "document": f"room_{self.room_id}_document",
            "key_value": f"room_{self.room_id}_key_value",
            "graph": f"room_{self.room_id}_graph",
            "time_series": f"room_{self.room_id}_time_series",
            "vector": f"room_{self.room_id}_vector",
            "in_memory": f"room_{self.room_id}_in_memory",
            "blockchain": f"room_{self.room_id}_blockchain",
            "new_sql": f"room_{self.room_id}_new_sql",
            "object_oriented": f"room_{self.room_id}_object_oriented",
            "spatial": f"room_{self.room_id}_spatial",
            # Additional specialized ones can be added
            "role_contributions": f"room_{self.room_id}_role_contributions",
            "voting_history": f"room_{self.room_id}_voting_history"
        }

    def query(self, db_type: str, query: Any) -> Any:
        """Query a specific database type in this room's bookshelf."""
        if db_type not in self.databases:
            raise ValueError(f"Unknown database type: {db_type}")
        # In real implementation, this would route to the actual DB layer with room scoping
        return {"db": self.databases[db_type], "result": f"Queried {db_type} for room {self.room_id}"}

    def store(self, db_type: str, data: Any) -> bool:
        """Store data into a specific database type in this room's bookshelf."""
        if db_type not in self.databases:
            raise ValueError(f"Unknown database type: {db_type}")
        # Real implementation would persist with room namespace
        return True

    def get_bookshelf_summary(self) -> Dict[str, str]:
        """Return overview of all 14 databases in this room's bookshelf."""
        return {k: v for k, v in self.databases.items()}
