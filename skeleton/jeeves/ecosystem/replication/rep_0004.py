"""Replication 0004.
"""
from __future__ import annotations

REP = "rep_0004"

def sync(fields: list[str]) -> dict:
    return {"ok": True, "rep": REP, "fields": fields[:12], "priority": "high" if 4 % 3 == 0 else "normal"}
