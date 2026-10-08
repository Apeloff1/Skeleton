"""Volume status. Seals are prior wc. This module does not read the trees."""

from __future__ import annotations

SEALS = (
    {"name": "organ", "files": 2368, "lines": 3329408, "done": True},
    {"name": "masterplan", "files": 200, "lines": 15302600, "done": True},
    {"name": "x10", "files": 200, "lines": 153003200, "done": True},
    {"name": "x100_shard", "files": 1, "lines": 7650009, "done": True},
    {"name": "eight", "files": 8, "lines": 100800072, "done": True},
    {"name": "clip_test", "files": 1, "lines": 0, "done": True},
    {"name": "on_main", "files": 1, "lines": 0, "done": True},
    {"name": "x100_full", "files": 200, "lines": 1530001800, "done": False},
    {"name": "deck", "files": 0, "lines": 0, "done": False},
    {"name": "ci_gate", "files": 0, "lines": 0, "done": False},
)


def percent() -> int:
    done = sum(1 for row in SEALS if row["done"])
    return round(100 * done / len(SEALS))


if __name__ == "__main__":
    print(percent())
