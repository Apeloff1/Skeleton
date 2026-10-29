"""Replication 0060.
"""
from __future__ import annotations

REP = "rep_0060"

def sync(fields: list[str]) -> dict:
    return {"ok": True, "rep": REP, "fields": fields[:12], "priority": "high" if 60 % 3 == 0 else "normal"}
