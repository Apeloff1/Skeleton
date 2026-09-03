"""GPU kernel plan + dispatch.

If a device is present, this is the launch card: tile, smem, registers,
occupancy guess. If not, every launch falls through to CPU fused ops.
No PTX is emitted. No .cu is compiled. That is not a stub — the
arithmetic is the CPU path; the GPU path is a scheduler over the same
shapes.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from skeleton.kernel.ops.device import probe
from skeleton.kernel.ops.engine import Engine
from skeleton.kernel.ops.fused import fused_block, naive_writes


class GpuKernel:
    """Launch geometry for one fused transformer block."""

    def __init__(self, d: int = 8, *, device: Optional[str] = None) -> None:
        self.dev = probe()
        if device:
            self.dev = {**self.dev, "device": device}
        self.d = max(4, min(64, int(d)))
        # Hopper-ish occupancy guess scaled down. Not a benchmark.
        self.tile = 16 if self.dev.get("cuda") else 8 if self.d >= 8 else 4
        self.smem = self.tile * self.d * 4 * 3  # Q/K/V tiles, bytes if fp32
        self.regs = 32 if self.dev.get("cuda") else 16
        self.engine = Engine(d=min(16, self.d))
        self.launches = 0
        self.fallback = 0

    def plan(self) -> Dict[str, Any]:
        return {
            "kind": "gpu-plan",
            "device": self.dev.get("device"),
            "d": self.d,
            "tile": self.tile,
            "smem_bytes": self.smem,
            "regs": self.regs,
            "grid": (1, 1, 1),
            "block": (self.tile, 1, 1),
            "stored_prose": 0,
        }

    def launch(self, x: List[float] | None = None) -> Dict[str, Any]:
        self.launches += 1
        # No device compiler. Same fused block. Card records the miss.
        if not self.dev.get("cuda") and self.dev.get("device") != "hip":
            self.fallback += 1
        step = self.engine.step(x)
        return {
            "kind": "gpu-launch",
            "plan": self.plan(),
            "fallback": int(bool(self.fallback)),
            "device": self.dev.get("device"),
            "writes": step.get("writes"),
            "naive": naive_writes(1, self.engine.d),
            "saved": step.get("saved"),
            "stored_prose": 0,
        }

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "kernel-gpu",
            "device": self.dev.get("device"),
            "launches": self.launches,
            "fallback": self.fallback,
            "plan": self.plan(),
            "ops": self.engine.card(),
            "stored_prose": 0,
        }
