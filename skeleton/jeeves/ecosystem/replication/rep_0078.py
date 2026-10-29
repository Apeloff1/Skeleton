"""Replication 0078.
"""
from __future__ import annotations

REP = "rep_0078"

def sync(fields: list[str]) -> dict:
    return {"ok": True, "rep": REP, "fields": fields[:12], "priority": "high" if 78 % 3 == 0 else "normal"}
