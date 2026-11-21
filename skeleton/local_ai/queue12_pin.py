"""
Queue-12 pin for local AI. RMSNorm + SiLU in attn, LoRA bank, beam, accum, gossip.
Add missing tests only. Do not re-derive.
"""
from __future__ import annotations

from .seam_runtime import admit, stamp

KERNELS = ["rmsnorm", "silu", "lora_bank", "beam", "accum", "gossip"]


def pin_kernels() -> list:
    return list(KERNELS)


def process(data: dict) -> dict:
    refused = admit("queue12_pin", data)
    if refused:
        return refused
    kernel = data.get("kernel")
    if kernel is None:
        return stamp("queue12_pin", data, {"kernels": KERNELS})
    if kernel not in KERNELS:
        return {
            "ok": False,
            "error": "unknown kernel",
            "card": "queue12_pin",
            "kernels": list(KERNELS),
        }
    return stamp("queue12_pin", data, {"kernels": KERNELS, "kernel": kernel})
