"""Replication 0017.
"""
from __future__ import annotations

REP = "rep_0017"

def sync(fields: list[str]) -> dict:
    return {"ok": True, "rep": REP, "fields": fields[:12], "priority": "high" if 17 % 3 == 0 else "normal"}
