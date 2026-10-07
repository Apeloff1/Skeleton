"""Boundary card. Unchanged protocol names."""

from __future__ import annotations

PROTOCOL = ("offer", "accept", "refuse", "expire")


def boundary() -> dict:
    return {"protocol": list(PROTOCOL), "n_cap": 8, "diet_fork": 0, "stored_prose": 0}
