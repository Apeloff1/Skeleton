"""Replication 0030.
"""
from __future__ import annotations

REP = "rep_0030"

def sync(fields: list[str]) -> dict:
    return {"ok": True, "rep": REP, "fields": fields[:12], "priority": "high" if 30 % 3 == 0 else "normal"}
