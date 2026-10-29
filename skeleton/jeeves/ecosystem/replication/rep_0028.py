"""Replication 0028.
"""
from __future__ import annotations

REP = "rep_0028"

def sync(fields: list[str]) -> dict:
    return {"ok": True, "rep": REP, "fields": fields[:12], "priority": "high" if 28 % 3 == 0 else "normal"}
