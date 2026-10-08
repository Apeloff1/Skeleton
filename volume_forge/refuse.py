"""Refuse a projection quoted as a census."""

from __future__ import annotations

CLAIMED = 280185289
PROJECTION = 1530001800


def refuse(quoted: int) -> dict[str, object]:
    if quoted == PROJECTION:
        raise RuntimeError("projection is not a census")
    if quoted != CLAIMED:
        raise RuntimeError("unknown count")
    return {"ok": True, "claimed": CLAIMED, "stored_prose": 0}


if __name__ == "__main__":
    print(refuse(CLAIMED))
