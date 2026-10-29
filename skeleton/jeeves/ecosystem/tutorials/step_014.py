"""Tutorial step 014.
"""
from __future__ import annotations

STEP = 14

def prompt() -> str:
    return f"Complete step {STEP} to continue."

def complete(done: bool) -> dict:
    return {"ok": bool(done), "step": STEP, "next": STEP + 1 if done else STEP}
