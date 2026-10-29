"""Replication 0008.
"""
from __future__ import annotations

REP = "rep_0008"

def sync(fields: list[str]) -> dict:
    return {"ok": True, "rep": REP, "fields": fields[:12], "priority": "high" if 8 % 3 == 0 else "normal"}
