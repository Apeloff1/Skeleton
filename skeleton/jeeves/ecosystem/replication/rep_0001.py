"""Replication 0001.
"""
from __future__ import annotations

REP = "rep_0001"

def sync(fields: list[str]) -> dict:
    return {"ok": True, "rep": REP, "fields": fields[:12], "priority": "high" if 1 % 3 == 0 else "normal"}
