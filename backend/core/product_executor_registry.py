"""Typed dispatch registry for governed product operations.

Executors register against exact (capability, action) contracts. Bindings are
versioned and declare their side-effect class plus replay-safety contract so the
control plane can introspect execution risk instead of treating every adapter as
an opaque callable. There are no wildcard fallbacks.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Literal

from core.product_operations import AdmittedOperation


ExecutorFn = Callable[[AdmittedOperation, dict], bool | Awaitable[bool]]
EffectClass = Literal["query", "state", "external"]


class ExecutorNotRegistered(LookupError):
    pass


@dataclass(frozen=True, slots=True)
class ExecutorBinding:
    capability_id: str
    action: str
    name: str
    executor: ExecutorFn
    version: int = 1
    effect_class: EffectClass = "state"
    replay_safe: bool = False


class ProductExecutorRegistry:
    def __init__(self) -> None:
        self._bindings: dict[tuple[str, str], ExecutorBinding] = {}

    def register(
        self,
        capability_id: str,
        action: str,
        executor: ExecutorFn,
        *,
        name: str | None = None,
        version: int = 1,
        effect_class: EffectClass = "state",
        replay_safe: bool = False,
    ) -> ExecutorBinding:
        capability_id = capability_id.strip()
        action = action.strip()
        if not capability_id or not action:
            raise ValueError("capability_id and action are required")
        if version <= 0:
            raise ValueError("executor version must be positive")
        if effect_class not in {"query", "state", "external"}:
            raise ValueError("invalid executor effect class")
        key = (capability_id, action)
        if key in self._bindings:
            raise ValueError(f"executor already registered for {capability_id}:{action}")
        binding = ExecutorBinding(
            capability_id=capability_id,
            action=action,
            name=name or getattr(executor, "__name__", "executor"),
            executor=executor,
            version=version,
            effect_class=effect_class,
            replay_safe=replay_safe,
        )
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

    def snapshot(self) -> tuple[dict[str, str | int | bool], ...]:
        return tuple(
            {
                "capability_id": binding.capability_id,
                "action": binding.action,
                "name": binding.name,
                "version": binding.version,
                "effect_class": binding.effect_class,
                "replay_safe": binding.replay_safe,
            }
            for _, binding in sorted(self._bindings.items())
        )

    def __len__(self) -> int:
        return len(self._bindings)
