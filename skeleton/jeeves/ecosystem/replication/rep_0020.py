"""Replication 0020.
"""
from __future__ import annotations

REP = "rep_0020"

def sync(fields: list[str]) -> dict:
    return {"ok": True, "rep": REP, "fields": fields[:12], "priority": "high" if 20 % 3 == 0 else "normal"}
