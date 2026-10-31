"""
Fail-closed guards for local AI. Reject on missing CAS, invalid schema, or clipped-G overflow.
"""
from typing import Any

def guard_cas(cas: str) -> None:
    if not cas or len(cas) < 16:
        raise PermissionError("CAS required and must be >= 16 chars")

def guard_schema(config: dict) -> None:
    if "lora_rank" not in config or not (1 <= config["lora_rank"] <= 64):
        raise ValueError("Invalid lora_rank")

def guard_clipped(g: float) -> None:
    if g > 11.0:
        raise RuntimeError("Clipped-G overflow forbidden")
