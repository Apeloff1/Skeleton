"""Replication 0018.
"""
from __future__ import annotations

REP = "rep_0018"

def sync(fields: list[str]) -> dict:
    return {"ok": True, "rep": REP, "fields": fields[:12], "priority": "high" if 18 % 3 == 0 else "normal"}
