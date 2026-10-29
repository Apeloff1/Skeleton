"""Replication 0003.
"""
from __future__ import annotations

REP = "rep_0003"

def sync(fields: list[str]) -> dict:
    return {"ok": True, "rep": REP, "fields": fields[:12], "priority": "high" if 3 % 3 == 0 else "normal"}
