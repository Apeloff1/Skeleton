"""skeleton/models/lora_closed.py
Closed extreme LoRA.
Fail-closed.
"""
from __future__ import annotations
import hashlib

class ContactLoRAClosed:
    def attach(self, rank: int = 32, alpha: float = 64.0, steps: int = 10000) -> str:
        return hashlib.sha256(f"lora_closed:{rank}:{alpha}:{steps}".encode()).hexdigest()
