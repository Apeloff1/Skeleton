"""Replication 0073.
"""
from __future__ import annotations

REP = "rep_0073"

def sync(fields: list[str]) -> dict:
    return {"ok": True, "rep": REP, "fields": fields[:12], "priority": "high" if 73 % 3 == 0 else "normal"}
