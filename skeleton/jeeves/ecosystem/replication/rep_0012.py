"""Replication 0012.
"""
from __future__ import annotations

REP = "rep_0012"

def sync(fields: list[str]) -> dict:
    return {"ok": True, "rep": REP, "fields": fields[:12], "priority": "high" if 12 % 3 == 0 else "normal"}
