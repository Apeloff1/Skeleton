"""Typed dispatch registry for governed product operations.

Executors register against exact (capability, action) contracts. There are no
wildcard fallbacks: unbound work remains pending instead of being silently
confirmed or routed to an unrelated legacy endpoint.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from core.product_operations import AdmittedOperation


ExecutorFn = Callable[[AdmittedOperation, dict[str, Any]], bool | Awaitable[bool]]


class ExecutorNotRegistered(LookupError):
    pass


@dataclass(frozen=True, slots=True)
class ExecutorBinding:
    capability_id: str
    action: str
    name: str
    executor: ExecutorFn


class ProductExecutorRegistry:
    def __init__(self) -> None:
        self._bindings: dict[tuple[str, str], ExecutorBinding] = {}

    def register(self, capability_id: str, action: str, executor: ExecutorFn, *, name: str | None = None) -> ExecutorBinding:
        capability_id = capability_id.strip()
        action = action.strip()
        if not capability_id or not action:
            raise ValueError("capability_id and action are required")
        key = (capability_id, action)
        if key in self._bindings:
            raise ValueError(f"executor already registered for {capability_id}:{action}")
        binding = ExecutorBinding(capability_id, action, name or getattr(executor, "__name__", "executor"), executor)
        self._bindings[key] = binding
        return binding

    def resolve(self, capability_id: str, action: str) -> ExecutorBinding | None:
        return self._bindings.get((capability_id, action))

    def require(self, capability_id: str, action: str) -> ExecutorBinding:
        binding = self.resolve(capability_id, action)
        if binding is None:
            raise ExecutorNotRegistered(f"no executor registered for {capability_id}:{action}")
        return binding

    def executor_for(self, operation: AdmittedOperation) -> ExecutorFn:
        return self.require(operation.capability_id, operation.action).executor

    def snapshot(self) -> tuple[dict[str, str], ...]:
        return tuple(
            {
                "capability_id": binding.capability_id,
                "action": binding.action,
                "name": binding.name,
            }
            for _, binding in sorted(self._bindings.items())
        )

    def __len__(self) -> int:
        return len(self._bindings)
