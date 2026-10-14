"""Volume status. Seals are prior wc. This module does not read the trees."""

from __future__ import annotations

SEALS = (
    {"name": "organ", "done": True},
    {"name": "masterplan", "done": True},
    {"name": "x10", "done": True},
    {"name": "x100_shard", "done": True},
    {"name": "eight", "done": True},
    {"name": "clip_test", "done": True},
    {"name": "on_main", "done": True},
    {"name": "deck_pointer", "done": True},
    {"name": "ci_gate", "done": True},
    {"name": "x100_full", "done": False},
)


def percent() -> int:
    done = sum(1 for row in SEALS if row["done"])
    return round(100 * done / len(SEALS))


if __name__ == "__main__":
    print(percent())
