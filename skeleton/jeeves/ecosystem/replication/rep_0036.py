"""Replication 0036.
"""
from __future__ import annotations

REP = "rep_0036"

def sync(fields: list[str]) -> dict:
    return {"ok": True, "rep": REP, "fields": fields[:12], "priority": "high" if 36 % 3 == 0 else "normal"}
