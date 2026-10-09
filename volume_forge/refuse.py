"""Refuse a projection quoted as a census.

Claimed sum is 280085289. The earlier 280185289 figure was a 100000 arithmetic error.
"""

from __future__ import annotations

CLAIMED = 280085289
PROJECTION = 1530001800


def refuse(quoted: int) -> dict[str, object]:
    if quoted == PROJECTION or quoted == 280185289:
        raise RuntimeError("not a census")
    if quoted != CLAIMED:
        raise RuntimeError("unknown count")
    return {"ok": True, "claimed": CLAIMED, "stored_prose": 0}


if __name__ == "__main__":
    print(refuse(CLAIMED))
