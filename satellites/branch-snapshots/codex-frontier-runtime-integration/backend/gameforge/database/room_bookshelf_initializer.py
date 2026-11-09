#!/usr/bin/env python3
"""
Room Bookshelf Initializer
Creates and initializes the full 14-database Bookshelf for every room on startup or reset.
"""

import json
from pathlib import Path
from typing import Dict

def initialize_room_bookshelf(room_id: str, category: str, output_dir: Path):
    """Create a fresh 14-database Bookshelf for a single room."""
    bookshelf = {
        "room_id": room_id,
        "category": category,
        "initialized_at": "2026-07-19T06:27:00Z",
        "version": "1.0",
        "databases": {
            "relational": {"type": "relational", "tables": ["roles", "seats", "contributions"]},
            "columnar": {"type": "columnar", "columns": ["role_id", "competency", "synergy_score"]},
            "document": {"type": "document", "collections": ["role_profiles", "performance_logs"]},
            "key_value": {"type": "key_value", "namespace": f"room:{room_id}"},
            "graph": {"type": "graph", "nodes": "roles", "edges": "synergy_links"},
            "time_series": {"type": "time_series", "metrics": ["coherence", "performance", "workload"]},
            "vector": {"type": "vector", "embedding_model": "role-semantic-v1"},
            "in_memory": {"type": "in_memory", "cache_size_mb": 512},
            "blockchain": {"type": "blockchain", "ledger": "role_contributions"},
            "new_sql": {"type": "new_sql", "hybrid_queries": True},
            "object_oriented": {"type": "object_oriented", "classes": ["Role", "Seat", "Contribution"]},
            "spatial": {"type": "spatial", "dimensions": ["category_space", "synergy_space"]},
            "role_contributions": {"type": "role_contributions", "records": []},
            "voting_history": {"type": "voting_history", "ballots": []}
        }
    }
    
    file_path = output_dir / f"{room_id}_bookshelf.json"
    with open(file_path, "w") as f:
        json.dump(bookshelf, f, indent=2)
    
    return file_path

def initialize_all_rooms(rooms_manifest_path: str, output_dir: Path):
    """Initialize Bookshelves for all rooms from manifest."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    with open(rooms_manifest_path, "r") as f:
        rooms = json.load(f)
    
    for room in rooms:
        initialize_room_bookshelf(room["room_id"], room["category"], output_dir)
    
    print(f"Initialized {len(rooms)} room Bookshelves.")

if __name__ == "__main__":
    initialize_all_rooms(
        "/home/workdir/artifacts/gameforge_v1/gameforge/manifests/rooms_manifest.json",
        Path("/home/workdir/artifacts/gameforge_v1/gameforge/database/bookshelves")
    )
