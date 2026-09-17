"""Stable name tables for law packs."""

from __future__ import annotations

STATUS = (
    "burn", "chill", "bleed", "ward", "daze", "focus", "fear", "lure",
    "lockshock", "vent", "ash", "fogmind", "coilpulse", "scrapcut", "overheat",
    "dreamlag", "extractready", "stalkmark", "jam", "spill", "quiet", "loud",
    "hungry", "fed", "keyed", "baited", "sleepless", "rested", "tracked",
    "hidden", "pressured", "relieved", "warped", "sealed", "doctored", "clipped",
    "spark", "rust", "dust", "echo", "hum", "drip", "glow", "shade", "grip",
    "slip", "thrum", "hush", "gnaw", "bloom", "wilt", "surge", "ebb", "bind",
    "loose", "marking",
)

VERBS = (
    "stoke", "vent", "wait", "sleep", "dream", "extract", "craft", "barter",
    "pick", "unlock", "bait", "hide", "sprint", "listen", "mark", "calm",
    "learn", "forget", "save", "load", "ascend", "descend", "jam", "spill",
    "fog", "clearfog", "coil", "spendcoil", "ward", "bleed", "mend", "scare",
    "soothe", "quest", "talk", "seal", "doctor", "clip", "warp", "handoff",
)


def counts() -> dict[str, int]:
    return {"status": len(STATUS), "verbs": len(VERBS), "stored_prose": 0}
