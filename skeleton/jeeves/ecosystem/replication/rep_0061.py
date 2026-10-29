"""Replication 0061.
"""
from __future__ import annotations

REP = "rep_0061"

def sync(fields: list[str]) -> dict:
    return {"ok": True, "rep": REP, "fields": fields[:12], "priority": "high" if 61 % 3 == 0 else "normal"}
