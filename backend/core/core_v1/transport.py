"""Delivery transports.

``HttpTransport`` posts with urllib, refuses redirects (a redirect could
bounce a signed payload to an internal host) and caps the response read.
``RecordingTransport`` is a scripted fake for tests and dry runs.
"""
from __future__ import annotations

import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Mapping

from skeleton.security.outbound_url import validate_public_https_url

from .ports import TransportResult

MAX_RESPONSE_BYTES = 8 * 1024
USER_AGENT = "Skeleton-Webhooks/1.0"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        return None


class PublicHttpsPolicy:
    """Default ``UrlPolicy``: public HTTPS only, via the shared outbound policy."""

    def check(self, url: str) -> str:
        value, _host = validate_public_https_url(url, purpose="webhook URL")
        return value


class HttpTransport:
    def __init__(self, policy: PublicHttpsPolicy | None = None) -> None:
        self.policy = policy or PublicHttpsPolicy()
        self._opener = urllib.request.build_opener(_NoRedirect)

    def post(self, url: str, body: bytes, headers: Mapping[str, str], timeout: float) -> TransportResult:
        try:
            url = self.policy.check(url)
        except ValueError as exc:
            return TransportResult(None, f"policy:{exc}")
        req = urllib.request.Request(url, data=body, method="POST",
                                     headers={"User-Agent": USER_AGENT, **headers})
        start = time.monotonic()
        try:
            with self._opener.open(req, timeout=timeout) as resp:
                resp.read(MAX_RESPONSE_BYTES)
                code = resp.status
            return TransportResult(code, "", (time.monotonic() - start) * 1000)
        except urllib.error.HTTPError as exc:
            return TransportResult(exc.code, f"http:{exc.code}", (time.monotonic() - start) * 1000)
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            return TransportResult(None, f"network:{type(exc).__name__}", (time.monotonic() - start) * 1000)


@dataclass
class RecordedCall:
    url: str
    body: bytes
    headers: dict[str, str]


@dataclass
class RecordingTransport:
    """Returns scripted responses; default 200. ``script`` may be a callable."""
    responses: list[TransportResult] = field(default_factory=list)
    responder: Callable[[RecordedCall], TransportResult] | None = None
    calls: list[RecordedCall] = field(default_factory=list)

    def post(self, url, body, headers, timeout) -> TransportResult:
        call = RecordedCall(url, body, dict(headers))
        self.calls.append(call)
        if self.responder is not None:
            return self.responder(call)
        if self.responses:
            return self.responses.pop(0)
        return TransportResult(200)


class AllowAllPolicy:
    """Test-only policy that accepts any https URL string."""

    def check(self, url: str) -> str:
        if not url.startswith("https://"):
            raise ValueError("webhook URL must use https")
        return url
