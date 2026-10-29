"""Replication 0010.
"""
from __future__ import annotations

REP = "rep_0010"

def sync(fields: list[str]) -> dict:
    return {"ok": True, "rep": REP, "fields": fields[:12], "priority": "high" if 10 % 3 == 0 else "normal"}
