"""Replication 0021.
"""
from __future__ import annotations

REP = "rep_0021"

def sync(fields: list[str]) -> dict:
    return {"ok": True, "rep": REP, "fields": fields[:12], "priority": "high" if 21 % 3 == 0 else "normal"}
