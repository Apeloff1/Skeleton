"""Bounded lifecycle hooks for shell execution.

Hooks receive metadata and results, never mutable runner internals.  Pre-hooks
may veto an execution by raising; post-hooks are observational and are isolated
so telemetry/audit behavior does not depend on optional integrations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping


@dataclass(frozen=True)
class ExecutionMetadata:
    command: str
    correlation_id: str
    fingerprint: str
    attempt: int
    session_id: str | None = None


PreHook = Callable[[ExecutionMetadata], None]
PostHook = Callable[[ExecutionMetadata, Any], None]


class HookRegistry:
    def __init__(
        self,
        *,
        pre: Iterable[PreHook] = (),
        post: Iterable[PostHook] = (),
        max_hooks: int = 32,
    ) -> None:
        if max_hooks <= 0:
            raise ValueError("max_hooks must be positive")
        self.max_hooks = max_hooks
        self._pre = list(pre)
        self._post = list(post)
        if len(self._pre) + len(self._post) > max_hooks:
            raise ValueError("hook count exceeds bound")

    def add_pre(self, hook: PreHook) -> None:
        if len(self._pre) + len(self._post) >= self.max_hooks:
            raise ValueError("hook count exceeds bound")
        self._pre.append(hook)

    def add_post(self, hook: PostHook) -> None:
        if len(self._pre) + len(self._post) >= self.max_hooks:
            raise ValueError("hook count exceeds bound")
        self._post.append(hook)

    def run_pre(self, metadata: ExecutionMetadata) -> None:
        for hook in tuple(self._pre):
            hook(metadata)

    def run_post(self, metadata: ExecutionMetadata, result: Any) -> tuple[str, ...]:
        failures: list[str] = []
        for hook in tuple(self._post):
            try:
                hook(metadata, result)
            except Exception as exc:  # observational hooks must not rewrite execution outcome
                failures.append(type(exc).__name__)
        return tuple(failures)

    def counts(self) -> Mapping[str, int]:
        return {"pre": len(self._pre), "post": len(self._post)}
