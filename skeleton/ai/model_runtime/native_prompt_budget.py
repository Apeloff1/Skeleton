"""Bounded ephemeral prompt-memory admission for guarded offline inference.

Prompt grants are not durable and cannot be replayed after restart. This ledger
accounts for UTF-8 prompt bytes staged in app RAM, independent of KV capacity,
GPU telemetry, disk spill and the durable execution-intent journal. The registry
owns the admission lock; the ledger additionally protects direct callers.
"""
from __future__ import annotations

from dataclasses import dataclass
from threading import RLock

MAX_PROMPT_BUDGET_BYTES = 16 << 20
MAX_TENANT_PROMPT_COUNT = 256


class PromptBudgetDenied(RuntimeError):
    """No prompt reservation was made; no model execution is authorized."""


@dataclass(frozen=True, slots=True)
class NativePromptBudget:
    """Explicit local RAM caps; zero, bool, negative and oversized are denied."""

    max_staged_bytes: int = 4 << 20
    max_staged_bytes_per_tenant: int = 1 << 20
    max_staged_per_tenant: int = 16

    def __post_init__(self) -> None:
        if (type(self.max_staged_bytes) is not int
                or not 1 <= self.max_staged_bytes <= MAX_PROMPT_BUDGET_BYTES):
            raise ValueError("invalid total staged prompt RAM cap")
        if (type(self.max_staged_bytes_per_tenant) is not int
                or not 1 <= self.max_staged_bytes_per_tenant <= self.max_staged_bytes):
            raise ValueError("invalid tenant staged prompt RAM cap")
        if (type(self.max_staged_per_tenant) is not int
                or not 1 <= self.max_staged_per_tenant <= MAX_TENANT_PROMPT_COUNT):
            raise ValueError("invalid tenant staged prompt count cap")


class PromptBudgetLedger:
    """No prompt content, request identifiers, secrets or tenant names in status.

    The app must hold its NativePromptRegistry lock around both a ledger
    mutation and its staged-grant mutation. This internal lock prevents
    inconsistent accounting if a trusted test or integration calls directly.
    A corrupted accounting invariant fails closed instead of resetting caps.
    """

    def __init__(self, budget: NativePromptBudget) -> None:
        if type(budget) is not NativePromptBudget:
            raise ValueError("canonical native prompt budget required")
        self._budget = budget
        self._lock = RLock()
        self._bytes = 0
        self._counts: dict[str, int] = {}
        self._tenant_bytes: dict[str, int] = {}

    @staticmethod
    def _tenant(tenant: object) -> str:
        if type(tenant) is not str or not tenant:
            raise PromptBudgetDenied("invalid tenant for prompt reservation")
        try:
            encoded = tenant.encode("utf-8", errors="strict")
        except UnicodeEncodeError as exc:
            raise PromptBudgetDenied("invalid tenant Unicode") from exc
        if len(encoded) > 128 or any(ord(c) < 32 or ord(c) == 127 for c in tenant):
            raise PromptBudgetDenied("invalid tenant for prompt reservation")
        return tenant

    @staticmethod
    def _size(size: object) -> int:
        if type(size) is not int or size < 1 or size > MAX_PROMPT_BUDGET_BYTES:
            raise PromptBudgetDenied("invalid prompt byte reservation")
        return size

    def _verify(self) -> None:
        if (self._bytes != sum(self._tenant_bytes.values())
                or set(self._counts) != set(self._tenant_bytes)
                or any(count < 1 for count in self._counts.values())
                or any(value < 1 for value in self._tenant_bytes.values())
                or self._bytes > self._budget.max_staged_bytes
                or any(count > self._budget.max_staged_per_tenant
                       for count in self._counts.values())
                or any(value > self._budget.max_staged_bytes_per_tenant
                       for value in self._tenant_bytes.values())):
            raise PromptBudgetDenied("prompt memory accounting invariant failed")

    def reserve(self, tenant: str, size: int) -> None:
        tenant = self._tenant(tenant)
        size = self._size(size)
        with self._lock:
            self._verify()
            count = self._counts.get(tenant, 0)
            tenant_bytes = self._tenant_bytes.get(tenant, 0)
            if (self._bytes + size > self._budget.max_staged_bytes
                    or tenant_bytes + size > self._budget.max_staged_bytes_per_tenant
                    or count >= self._budget.max_staged_per_tenant):
                raise PromptBudgetDenied("staged prompt RAM admission denied")
            self._counts[tenant] = count + 1
            self._tenant_bytes[tenant] = tenant_bytes + size
            self._bytes += size
            self._verify()

    def release(self, tenant: str, size: int) -> None:
        tenant = self._tenant(tenant)
        size = self._size(size)
        with self._lock:
            self._verify()
            count = self._counts.get(tenant, 0)
            tenant_bytes = self._tenant_bytes.get(tenant, 0)
            if count < 1 or tenant_bytes < size:
                raise PromptBudgetDenied("unowned prompt reservation release")
            if count == 1 and tenant_bytes != size:
                raise PromptBudgetDenied("last prompt reservation accounting mismatch")
            if count > 1 and tenant_bytes <= size:
                raise PromptBudgetDenied("prompt reservation count mismatch")
            if count == 1:
                del self._counts[tenant]
                del self._tenant_bytes[tenant]
            else:
                self._counts[tenant] = count - 1
                self._tenant_bytes[tenant] = tenant_bytes - size
                if self._tenant_bytes[tenant] == 0:
                    raise PromptBudgetDenied("prompt reservation count mismatch")
            self._bytes -= size
            self._verify()

    def snapshot(self) -> dict[str, int | str]:
        with self._lock:
            self._verify()
            return {
                "schema": "skeleton.ai.native-prompt-memory-budget.v1",
                "staged_bytes": self._bytes,
                "staged_grants": sum(self._counts.values()),
                "active_tenants": len(self._counts),
                "max_staged_bytes": self._budget.max_staged_bytes,
                "max_staged_bytes_per_tenant": self._budget.max_staged_bytes_per_tenant,
                "max_staged_per_tenant": self._budget.max_staged_per_tenant,
            }
