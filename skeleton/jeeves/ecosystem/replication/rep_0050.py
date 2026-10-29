"""Replication 0050.
"""
from __future__ import annotations

REP = "rep_0050"

def sync(fields: list[str]) -> dict:
    return {"ok": True, "rep": REP, "fields": fields[:12], "priority": "high" if 50 % 3 == 0 else "normal"}
