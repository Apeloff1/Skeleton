"""Fail-closed local-only readiness probes for consumer setup.

HTTP success is not native GGUF, Windows device or release evidence.
"""
from __future__ import annotations
import json
from typing import Callable
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler

SERVICES = frozenset({"backend", "local_ai", "jeeves", "builder", "game_store"})
MAX_BODY = 4096

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def loopback_probe(service: str, url: str, *, timeout: float = 1.5) -> Callable[[], bool]:
    """Return an observable probe; never follow redirects or send credentials."""
    if service not in SERVICES:
        raise ValueError("unknown-service")
    if not isinstance(url, str) or len(url) > 512:
        raise ValueError("invalid-url")
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("invalid-url") from exc
    if (parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "::1")
            or port is None or parsed.username or parsed.password
            or parsed.query or parsed.fragment
            or parsed.path not in ("/health", "/health/ready", "/api/health")):
        raise ValueError("loopback-required")
    if type(timeout) not in (int, float) or not 0 < timeout <= 5:
        raise ValueError("invalid-timeout")
    def probe() -> bool:
        try:
            request = Request(url, headers={"Accept": "application/json"}, method="GET")
            with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=timeout) as response:
                if response.status != 200 or response.headers.get_content_type() != "application/json":
                    return False
                body = response.read(MAX_BODY + 1)
            if len(body) > MAX_BODY:
                return False
            data = json.loads(body)
            if type(data) is not dict or data.get("service") != service or data.get("ready") is not True:
                return False
            if service == "local_ai":
                return (data.get("guard_active") is True
                        and data.get("model_bound") is True
                        and data.get("reviewer_active") is True)
            return True
        except (OSError, ValueError, TypeError):
            return False

    return probe
