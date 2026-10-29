"""Level layout 048.
"""
from __future__ import annotations

LAYOUT = "layout_048"

def rooms(optical: float = 0.9) -> list[dict]:
    n = 4 + (48 % 6)
    out = []
    for r in range(n):
        kind = "boss" if r == n - 1 else ("shop" if r % 4 == 0 else "combat")
        out.append({"id": r, "kind": kind, "optical": round(optical, 3)})
    return out

def connections(count: int) -> list[list[int]]:
    count = max(2, int(count))
    return [[i, i + 1] for i in range(count - 1)]
