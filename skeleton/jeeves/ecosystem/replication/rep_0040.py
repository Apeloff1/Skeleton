"""Replication 0040.
"""
from __future__ import annotations

REP = "rep_0040"

def sync(fields: list[str]) -> dict:
    return {"ok": True, "rep": REP, "fields": fields[:12], "priority": "high" if 40 % 3 == 0 else "normal"}
