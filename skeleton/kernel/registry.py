"""
Skeleton Kernel — Registry module (canonical home)
"""

from __future__ import annotations

from skeleton.kernel.primitives import CapabilityRegistry

__all__ = ["CapabilityRegistry"]

class CapabilityKind:
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"

class CapabilityRegistry:
    def __init__(self):
        self.capabilities = {}
    def register(self, kind, handler):
        self.capabilities[kind] = handler

def bootstrap_registry():
    return CapabilityRegistry()
