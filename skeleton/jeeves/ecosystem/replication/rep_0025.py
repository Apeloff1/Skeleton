"""Replication 0025.
"""
from __future__ import annotations

REP = "rep_0025"

def sync(fields: list[str]) -> dict:
    return {"ok": True, "rep": REP, "fields": fields[:12], "priority": "high" if 25 % 3 == 0 else "normal"}
