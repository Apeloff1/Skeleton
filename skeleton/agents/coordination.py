"""Agent coordination — exclusive slot claiming via kernel leases.

One slot, one holder. The coordinator rides the kernel ``LeaseManager``
so claims expire and can be handed off deliberately, not by accident.
"""

from __future__ import annotations

from typing import Optional

from skeleton.kernel.errors import AgentError
from skeleton.kernel.leases import Lease, LeaseError, LeaseManager


class ClaimError(AgentError):
    code = "AGT.CLAIM"


class Coordinator:
    """Exclusive slot claims for agent roles (leader-of-queues, schedulers)."""

    def __init__(self, manager: Optional[LeaseManager] = None) -> None:
        self._manager = manager or LeaseManager()

    def claim(self, slot: str, agent: str, ttl_s: float = 30.0) -> Lease:
        try:
            return self._manager.acquire(slot, agent, ttl_s=ttl_s)
        except LeaseError as exc:
            raise ClaimError(
                "slot already claimed",
                context={"slot": slot, "current": getattr(exc, "holder", None)},
            )

    def renew(self, slot: str, agent: str, lease: Lease) -> Lease:
        try:
            return self._manager.renew(slot, agent, lease.fence)
        except LeaseError as exc:
            raise ClaimError("renew failed", context={"slot": slot, "agent": agent})

    def release(self, slot: str, agent: str) -> bool:
        return self._manager.release(slot, agent)

    def owner(self, slot: str) -> Optional[str]:
        lease = self._manager.current(slot)
        return lease.holder if lease else None
