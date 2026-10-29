"""Replication 0062.
"""
from __future__ import annotations

REP = "rep_0062"

def sync(fields: list[str]) -> dict:
    return {"ok": True, "rep": REP, "fields": fields[:12], "priority": "high" if 62 % 3 == 0 else "normal"}
