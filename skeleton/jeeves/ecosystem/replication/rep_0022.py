"""Replication 0022.
"""
from __future__ import annotations

REP = "rep_0022"

def sync(fields: list[str]) -> dict:
    return {"ok": True, "rep": REP, "fields": fields[:12], "priority": "high" if 22 % 3 == 0 else "normal"}
