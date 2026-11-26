"""Process-wide bounded DNS admission for GameForge's outbound HTTP clients.

A coroutine timeout cannot stop a running OS resolver. Keep its admission
permit until the *physical* worker exits, including after caller cancellation.
Never hold open an unbounded queue of abandoned resolver submissions.
"""
from __future__ import annotations

import asyncio
import ipaddress
import math
import threading
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from typing import TypeVar

_T = TypeVar("_T")
_MAX_PENDING_DNS = 8
_MAX_ACTIVE_EGRESS = 16


class ResolverCapacityError(RuntimeError):
    """All admitted resolver workers are still outstanding."""


class BoundedResolver:
    """Nonblocking admission across event loops and request owners."""

    def __init__(self, capacity: int = _MAX_PENDING_DNS) -> None:
        if type(capacity) is not int or not 1 <= capacity <= 64:
            raise ValueError("invalid resolver capacity")
        self._slots = threading.BoundedSemaphore(capacity)

    async def run(
        self, resolver: Callable[..., _T], *args: object, timeout: float = 5.0
    ) -> _T:
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
            raise ValueError("invalid resolver timeout")
        if not 0 < timeout <= 30 or not math.isfinite(timeout):
            raise ValueError("invalid resolver timeout")
        loop = asyncio.get_running_loop()
        if not self._slots.acquire(blocking=False):
            raise ResolverCapacityError("outbound DNS capacity exhausted")

        def worker() -> _T:
            try:
                return resolver(*args)
            finally:
                self._slots.release()

        try:
            future = loop.run_in_executor(None, worker)
        except BaseException:
            self._slots.release()
            raise

        def consume(completed: asyncio.Future[_T]) -> None:
            # The original caller may have timed out. Consume a late error to
            # avoid an unhandled-future warning or accidental credential logs.
            if not completed.cancelled():
                completed.exception()

        future.add_done_callback(consume)
        return await asyncio.wait_for(asyncio.shield(future), timeout=timeout)


class EgressCapacityError(RuntimeError):
    """The process-wide outbound work budget has been exhausted."""


class EgressAdmission:
    """Bound concurrent outbound exchanges without queueing request objects."""

    def __init__(self, capacity: int = _MAX_ACTIVE_EGRESS) -> None:
        if type(capacity) is not int or not 1 <= capacity <= 128:
            raise ValueError("invalid egress capacity")
        self._slots = threading.BoundedSemaphore(capacity)

    @contextmanager
    def slot(self) -> Iterator[None]:
        if not self._slots.acquire(blocking=False):
            raise EgressCapacityError("outbound HTTP capacity exhausted")
        try:
            yield
        finally:
            self._slots.release()


DNS_RESOLVER = BoundedResolver()
HTTP_ADMISSION = EgressAdmission()


def is_public_egress_address(value: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Reject non-unicast and scoped endpoints even if is_global says true."""
    if not value.is_global or value.is_multicast or value.is_reserved:
        return False
    if isinstance(value, ipaddress.IPv6Address):
        # DNS must provide native unscoped addresses. Avoid transition forms
        # whose embedded address or local scope can change routing semantics.
        if (
            value.scope_id is not None
            or value.ipv4_mapped is not None
            or value.sixtofour is not None
            or value.teredo is not None
        ):
            return False
    return True


def require_identity_encoding(headers: Mapping[str, str]) -> None:
    """Reject unsolicited compression before HTTPX can inflate a hostile chunk.

    Both clients request identity transfer. The byte budget then applies to
    the actual application payload, without a decompression allocation gap.
    """
    coding = headers.get("content-encoding", "")
    if type(coding) is not str or coding.strip().lower() not in ("", "identity"):
        raise ValueError("compressed external response is not admitted")
