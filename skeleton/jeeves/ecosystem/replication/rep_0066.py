"""Replication 0066.
"""
from __future__ import annotations

REP = "rep_0066"

def sync(fields: list[str]) -> dict:
    return {"ok": True, "rep": REP, "fields": fields[:12], "priority": "high" if 66 % 3 == 0 else "normal"}
