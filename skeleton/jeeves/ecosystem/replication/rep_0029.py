"""Replication 0029.
"""
from __future__ import annotations

REP = "rep_0029"

def sync(fields: list[str]) -> dict:
    return {"ok": True, "rep": REP, "fields": fields[:12], "priority": "high" if 29 % 3 == 0 else "normal"}
