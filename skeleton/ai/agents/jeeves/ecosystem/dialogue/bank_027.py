"""Dialogue bank 027.
"""
from __future__ import annotations

BANK = "dialogue_027"

def line(speaker: str, mood: str = "neutral") -> dict:
    if not speaker:
        return {"ok": False, "reason": "no_speaker"}
    return {"ok": True, "bank": BANK, "speaker": speaker, "mood": mood, "text": f"{speaker} speaks ({mood})."}

def choices() -> list[str]:
    return ["continue", "ask", "leave"]
