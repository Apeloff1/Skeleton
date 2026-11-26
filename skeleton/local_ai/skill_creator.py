"""
Guide for creating and updating skills that extend the agent's capabilities.
"""
from __future__ import annotations

import re

from .seam_runtime import admit, stamp

SKILLS: list[str] = []
_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
_CAP = 64


def create(name: str) -> None:
    if not isinstance(name, str) or not _NAME.fullmatch(name):
        raise ValueError("skill name is invalid")
    if name in SKILLS:
        return
    if len(SKILLS) >= _CAP:
        raise ValueError("skill list is full")
    SKILLS.append(name)


def process(data: dict) -> dict:
    refused = admit("skill_creator", data)
    if refused:
        return refused
    name = data.get("name")
    if name is None:
        return stamp("skill_creator", data, {"skills": SKILLS, "count": len(SKILLS)})
    try:
        create(name)
    except ValueError as exc:
        return {"ok": False, "error": str(exc), "card": "skill_creator"}
    return stamp("skill_creator", data, {"skills": SKILLS, "count": len(SKILLS), "name": name})
