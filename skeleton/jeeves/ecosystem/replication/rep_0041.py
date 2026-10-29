"""Replication 0041.
"""
from __future__ import annotations

REP = "rep_0041"

def sync(fields: list[str]) -> dict:
    return {"ok": True, "rep": REP, "fields": fields[:12], "priority": "high" if 41 % 3 == 0 else "normal"}
