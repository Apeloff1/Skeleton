"""Replication 0009.
"""
from __future__ import annotations

REP = "rep_0009"

def sync(fields: list[str]) -> dict:
    return {"ok": True, "rep": REP, "fields": fields[:12], "priority": "high" if 9 % 3 == 0 else "normal"}
