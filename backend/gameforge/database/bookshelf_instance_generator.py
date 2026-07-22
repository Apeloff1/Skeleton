#!/usr/bin/env python3
"""
Bookshelf Instance Generator for Zaibatsu CNS
Generates per-room 14-database Bookshelf instances with full schema support.
"""

import json
from pathlib import Path
from typing import Dict, List

BOOKSHELF_TYPES = [
    "relational", "columnar", "document", "key_value", "graph",
    "time_series", "vector", "in_memory", "blockchain", "new_sql",
    "object_oriented", "spatial", "role_contributions", "voting_history"
]

def generate_bookshelf_instance(room_id: str, category: str) -> Dict:
    """Generate a full 14-database Bookshelf instance for a room."""
    instance = {
        "room_id": room_id,
        "category": category,
        "created_at": "2026-07-19T06:27:00Z",
        "databases": {}
    }
    
    for db_type in BOOKSHELF_TYPES:
        instance["databases"][db_type] = {
            "type": db_type,
            "status": "active",
            "schema_version": "1.0",
            "index_enabled": True,
            "coherence_enforced": True,
            "synergy_links": [],
            "role_contributions": [] if db_type == "role_contributions" else None,
            "voting_history": [] if db_type == "voting_history" else None
        }
    
    return instance

def generate_all_room_bookshelves(rooms: List[Dict]) -> None:
    """Generate Bookshelf instances for all rooms."""
    output_dir = Path("/home/workdir/artifacts/gameforge_v1/gameforge/database/bookshelves")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    for room in rooms:
        instance = generate_bookshelf_instance(room["room_id"], room["category"])
        file_path = output_dir / f"{room['room_id']}_bookshelf.json"
        with open(file_path, "w") as f:
            json.dump(instance, f, indent=2)
    
    print(f"Generated {len(rooms)} Bookshelf instances in {output_dir}")

if __name__ == "__main__":
    # Example usage - would be fed from room manifest
    sample_rooms = [
        {"room_id": "room_research_001", "category": "research"},
        {"room_id": "room_engineering_001", "category": "engineering"},
        # ... all 1000 rooms
    ]
    generate_all_room_bookshelves(sample_rooms)
