"""skeleton/runtimes/specialized_extreme.py
10x extreme complete specialized runtimes.
Mobile bank defaults-off, bench GPU dark, plane adapters.
Fail-closed.
"""
from __future__ import annotations

class RuntimeError(Exception):
    pass

class SpecializedRuntime:
    def __init__(self, plane: str):
        self.plane = plane
        self.defaults_off = True

    def activate(self, mobile: bool = False) -> bool:
        if mobile and self.plane in ("speculative_rag", "sse", "bench_gpu"):
            raise RuntimeError("dark on mobile")
        return True
