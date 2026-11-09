"""Prefill / decode pipeline over the fused block.

Pointer: DistServe + Orca. House mapping: split budget then one
fused_block per phase. Prefill packs a short bag. Decode steps one
token. GPU launch is the same card; device may be cpu.
"""
from __future__ import annotations

from typing import Any, Dict, List

def _tok(text: str):
    return [p for p in (text or "plan tensor ttk").lower().replace("-", " ").split() if len(p) >= 3]


class Pipeline:
    def __init__(self, *, mobile: bool = True) -> None:
        self.mobile = bool(mobile)
        self.prefills = 0
        self.decodes = 0
        self.blocked = 0

    def run(self, text: str = "", *, bank: Dict[str, Any] | None = None) -> Dict[str, Any]:
        bank = bank or {}
        split = bank.get("split")
        ops = bank.get("ops")
        gpu = bank.get("gpu")
        ram = bank.get("ram")
        tokens = _tok(text)[: 4 if self.mobile else 8]
        phases: List[str] = []
        if split is None or split.take("prefill"):
            if ram is not None and hasattr(ram, "put"):
                for tok in tokens:
                    ram.put(tok, need=16)
            if gpu is not None and hasattr(gpu, "launch"):
                gpu.launch()
            elif ops is not None and hasattr(ops, "step"):
                ops.step()
            self.prefills += 1
            phases.append("prefill")
        else:
            self.blocked += 1
        if split is None or split.take("decode"):
            if ops is not None and hasattr(ops, "step"):
                ops.step()
            self.decodes += 1
            phases.append("decode")
        else:
            self.blocked += 1
        return {
            "kind": "kernel-pipeline",
            "phases": phases,
            "tokens": tokens,
            "prefills": self.prefills,
            "decodes": self.decodes,
            "blocked": self.blocked,
            "stored_prose": 0,
        }

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "kernel-pipeline",
            "prefills": self.prefills,
            "decodes": self.decodes,
            "blocked": self.blocked,
            "stored_prose": 0,
        }
