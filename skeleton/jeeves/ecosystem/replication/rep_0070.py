"""Replication 0070.
"""
from __future__ import annotations

REP = "rep_0070"

def sync(fields: list[str]) -> dict:
    return {"ok": True, "rep": REP, "fields": fields[:12], "priority": "high" if 70 % 3 == 0 else "normal"}
