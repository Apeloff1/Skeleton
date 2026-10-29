"""Replication 0023.
"""
from __future__ import annotations

REP = "rep_0023"

def sync(fields: list[str]) -> dict:
    return {"ok": True, "rep": REP, "fields": fields[:12], "priority": "high" if 23 % 3 == 0 else "normal"}
