"""Replication 0071.
"""
from __future__ import annotations

REP = "rep_0071"

def sync(fields: list[str]) -> dict:
    return {"ok": True, "rep": REP, "fields": fields[:12], "priority": "high" if 71 % 3 == 0 else "normal"}
