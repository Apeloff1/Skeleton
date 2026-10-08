"""Claim card for the volume plane on Skeleton main.

Only measured seals are claimed. A projection is not a claim.
"""

from __future__ import annotations

CLAIMED = (
    {"name": "organ", "lines": 3329408, "census": "census.py"},
    {"name": "masterplan", "lines": 15302600, "census": "wc"},
    {"name": "x10", "lines": 153003200, "census": "wc"},
    {"name": "x100_shard", "lines": 7650009, "census": "wc"},
    {"name": "eight", "lines": 100800072, "census": "wc"},
)
UNCLAIMED = ("x100_full_200_shards",)


def claim() -> dict[str, object]:
    lines = sum(row["lines"] for row in CLAIMED)
    return {
        "repo": "Apeloff1/Skeleton",
        "branch": "main",
        "plane": "volume",
        "claimed_lines": lines,
        "claimed": [row["name"] for row in CLAIMED],
        "unclaimed": list(UNCLAIMED),
        "stored_prose": 0,
        "clip": 1.1,
    }


if __name__ == "__main__":
    print(claim())
