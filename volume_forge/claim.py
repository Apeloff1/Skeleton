"""Claim card. Sum is 280085289. 280185289 was an arithmetic error."""

from __future__ import annotations

CLAIMED = (
    {"name": "organ", "lines": 3329408},
    {"name": "masterplan", "lines": 15302600},
    {"name": "x10", "lines": 153003200},
    {"name": "x100_shard", "lines": 7650009},
    {"name": "eight", "lines": 100800072},
)


def claim() -> dict[str, object]:
    lines = sum(row["lines"] for row in CLAIMED)
    if lines != 280085289:
        raise RuntimeError("sum drift")
    return {"repo": "Apeloff1/Skeleton", "branch": "main", "claimed_lines": lines, "stored_prose": 0}


if __name__ == "__main__":
    print(claim())
