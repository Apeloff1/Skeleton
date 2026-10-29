"""Replication 0015.
"""
from __future__ import annotations

REP = "rep_0015"

def sync(fields: list[str]) -> dict:
    return {"ok": True, "rep": REP, "fields": fields[:12], "priority": "high" if 15 % 3 == 0 else "normal"}
