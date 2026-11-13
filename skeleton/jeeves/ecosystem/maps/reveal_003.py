"""Map reveal 003.
"""
from __future__ import annotations

MAP = "map_003"

def reveal(room_id: int, known: list[int]) -> list[int]:
    out = list(known)
    if room_id not in out:
        out.append(room_id)
    return out

def fog(total: int, known: list[int]) -> float:
    if total <= 0:
        return 1.0
    return round(1.0 - len(known) / total, 3)
