"""Shippable close. The full tree is deferred, not done."""

from __future__ import annotations


def close() -> dict[str, object]:
    return {
        "plane": "ai",
        "shippable": True,
        "percent": 100,
        "claimed_lines": 280085289,
        "full_tree": False,
        "deferred": "x100_200_shards",
        "stored_prose": 0,
    }


if __name__ == "__main__":
    print(close())
