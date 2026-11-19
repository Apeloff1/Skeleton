"""Process-local revalidation envelope for an already-issued CPU permit.

The dispatcher retains the original raw planning ceiling, not a second grant.
The scoped envelope only survives synchronous trusted owner invocation. It is
not serialized in checkpoints, recovered after restart, or accepted from an
HTTP caller. Every fresh sample may reduce but never enlarge the permit.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import os
import threading
from typing import Iterator

from .fair_stream_queue import MAX_TOKENS
from .fair_stream_session import DispatchPermit

@dataclass(slots=True)
class _ExecutionScope:
    permit: DispatchPermit
    ceiling: int
    pid: int
    thread: int
    active: bool = True


_scope: ContextVar[_ExecutionScope | None] = ContextVar(
    "fair_stream_revalidation", default=None,
)


@contextmanager
def bound_revalidation_budget(permit: DispatchPermit, token_budget: int) -> Iterator[None]:
    if (type(permit) is not DispatchPermit or type(permit.tokens) is not int
            or type(token_budget) is not int
            or not 1 <= permit.tokens <= token_budget <= MAX_TOKENS
            or _scope.get() is not None):
        raise ValueError("canonical non-nested revalidation envelope required")
    scope = _ExecutionScope(permit, token_budget, os.getpid(), threading.get_ident())
    token = _scope.set(scope)
    try:
        yield
    finally:
        # copy_context() preserves object identity. Revocation must affect
        # every copied context, not solely the original ContextVar binding.
        scope.active = False
        _scope.reset(token)


def revalidation_budget(permit: DispatchPermit) -> int:
    observed = _scope.get()
    if observed is None:
        # Standalone callers have no original planning witness. Preserve
        # conservative revalidation rather than inventing a larger ceiling.
        return permit.tokens
    if (not observed.active or observed.permit is not permit
            or observed.pid != os.getpid()
            or observed.thread != threading.get_ident()):
        raise ValueError("revalidation envelope does not bind this execution")
    return observed.ceiling
