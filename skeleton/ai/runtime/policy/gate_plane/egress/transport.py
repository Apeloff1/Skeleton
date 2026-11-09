"""Transports for the egress gateway.

``Transport`` is ``transport(request) -> TransportResponse`` and may raise
``ConnectionError`` / ``TimeoutError`` / ``OSError`` for transient failures
(classified as retryable by the pipeline). Redirects are **never** followed:
a 3xx from a webhook receiver could point at an internal address and bypass
the allowlist, so it is reported as a non-retryable failure instead.

* :class:`UrllibTransport` — stdlib HTTP client, no redirects, bounded
  response read, per-attempt timeout from the pipeline deadline.
* :class:`ScriptedTransport` — deterministic fake for tests and chaos runs.
"""

from __future__ import annotations

import threading
import urllib.error
import urllib.request
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable, Deque, Dict, List, Mapping, Optional, Protocol, Tuple, Union

MAX_RESPONSE_BYTES = 64 * 1024
USER_AGENT = "skeleton-gate-plane-egress/1"


@dataclass(frozen=True)
class TransportRequest:
    method: str
    url: str
    headers: Mapping[str, str]
    body: bytes
    timeout_s: float
    pinned_addresses: Tuple[str, ...] = ()


@dataclass(frozen=True)
class TransportResponse:
    status: int
    headers: Tuple[Tuple[str, str], ...] = ()
    body: bytes = b""

    def header(self, name: str) -> Optional[str]:
        low = name.lower()
        for k, v in self.headers:
            if k.lower() == low:
                return v
        return None


class Transport(Protocol):
    def __call__(self, request: TransportRequest) -> TransportResponse: ...


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:  # type: ignore[override]
        return None


class UrllibTransport:
    def __init__(self, *, max_response_bytes: int = MAX_RESPONSE_BYTES) -> None:
        self.max_response_bytes = int(max_response_bytes)
        self._opener = urllib.request.build_opener(_NoRedirect())

    def __call__(self, request: TransportRequest) -> TransportResponse:
        headers = {"user-agent": USER_AGENT, **dict(request.headers)}
        req = urllib.request.Request(request.url, data=request.body, method=request.method, headers=headers)
        timeout = max(0.001, float(request.timeout_s))
        try:
            with self._opener.open(req, timeout=timeout) as resp:  # nosec B310 - URL vetted by EgressAllowlist
                body = resp.read(self.max_response_bytes)
                return TransportResponse(int(resp.status), tuple(resp.headers.items()), body)
        except urllib.error.HTTPError as exc:
            body = exc.read(self.max_response_bytes) if exc.fp is not None else b""
            hdrs = tuple(exc.headers.items()) if exc.headers is not None else ()
            return TransportResponse(int(exc.code), hdrs, body)
        except urllib.error.URLError as exc:
            reason = exc.reason
            if isinstance(reason, TimeoutError):
                raise TimeoutError(str(reason)) from None
            raise ConnectionError(str(reason)) from None


Step = Union[int, TransportResponse, BaseException, Callable[[TransportRequest], TransportResponse]]


class ScriptedTransport:
    """Plays back a script per URL (or a default script), recording every request.

    Steps: an ``int`` status, a :class:`TransportResponse`, an exception
    instance (raised), or a callable. When a script runs dry the
    ``default`` step repeats (200 unless set).
    """

    def __init__(self, default: Step = 200, *, clock: Any = None, latency_s: float = 0.0) -> None:
        self.default = default
        self.clock = clock
        self.latency_s = float(latency_s)
        self._scripts: Dict[str, Deque[Step]] = {}
        self._lock = threading.Lock()
        self.requests: List[TransportRequest] = []

    def script(self, url: str, *steps: Step) -> "ScriptedTransport":
        with self._lock:
            self._scripts.setdefault(url, deque()).extend(steps)
        return self

    def calls_to(self, url: str) -> List[TransportRequest]:
        return [r for r in self.requests if r.url == url]

    def __call__(self, request: TransportRequest) -> TransportResponse:
        with self._lock:
            self.requests.append(request)
            queue = self._scripts.get(request.url)
            step = queue.popleft() if queue else self.default
        if self.latency_s and self.clock is not None:
            self.clock.advance(self.latency_s)
        if isinstance(step, BaseException):
            raise step
        if isinstance(step, int):
            return TransportResponse(step)
        if isinstance(step, TransportResponse):
            return step
        return step(request)


__all__ = [
    "MAX_RESPONSE_BYTES",
    "ScriptedTransport",
    "Transport",
    "TransportRequest",
    "TransportResponse",
    "UrllibTransport",
]
