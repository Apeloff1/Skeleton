"""Replication 0013.
"""
from __future__ import annotations

REP = "rep_0013"

def sync(fields: list[str]) -> dict:
    return {"ok": True, "rep": REP, "fields": fields[:12], "priority": "high" if 13 % 3 == 0 else "normal"}
