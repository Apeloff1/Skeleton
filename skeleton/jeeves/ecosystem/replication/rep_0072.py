"""Replication 0072.
"""
from __future__ import annotations

REP = "rep_0072"

def sync(fields: list[str]) -> dict:
    return {"ok": True, "rep": REP, "fields": fields[:12], "priority": "high" if 72 % 3 == 0 else "normal"}
