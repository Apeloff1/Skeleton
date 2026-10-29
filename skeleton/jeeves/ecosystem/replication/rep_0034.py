"""Replication 0034.
"""
from __future__ import annotations

REP = "rep_0034"

def sync(fields: list[str]) -> dict:
    return {"ok": True, "rep": REP, "fields": fields[:12], "priority": "high" if 34 % 3 == 0 else "normal"}
