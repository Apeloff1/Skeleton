"""Season fence — one walker at a time on this bank."""
from __future__ import annotations

from typing import Any, Dict

from skeleton.kernel.leases import LeaseHeldError, LeaseManager


class Fence:
    def __init__(self) -> None:
        self.mgr = LeaseManager(ttl_s=30.0)
        self.held = 0
        self.denied = 0

    def acquire(self) -> bool:
        try:
            self.mgr.acquire("season", "orch")
            self.held += 1
            return True
        except LeaseHeldError:
            self.denied += 1
            return False

    def release(self) -> None:
        try:
            self.mgr.release("season", "orch")
        except Exception:
            pass

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "kernel-fence",
            "held": self.held,
            "denied": self.denied,
            "stored_prose": 0,
        }
