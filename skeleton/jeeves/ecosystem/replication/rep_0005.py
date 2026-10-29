"""Replication 0005.
"""
from __future__ import annotations

REP = "rep_0005"

def sync(fields: list[str]) -> dict:
    return {"ok": True, "rep": REP, "fields": fields[:12], "priority": "high" if 5 % 3 == 0 else "normal"}
