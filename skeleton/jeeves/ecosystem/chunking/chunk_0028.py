"""Chunk 0028.
"""
from __future__ import annotations

CHUNK = "chunk_0028"

def split(data: str, size: int = 64) -> list[str]:
    if not data:
        return []
    size = max(8, min(256, size))
    return [data[j:j+size] for j in range(0, len(data), size)]
