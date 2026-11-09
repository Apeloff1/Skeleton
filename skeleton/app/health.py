"""HTTP smoke probes for the assembled application."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping
import math
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from skeleton.app.assembly import AssemblyManifest, ServiceSpec, load_manifest


@dataclass(frozen=True)
class ProbeResult:
    service: str
    url: str
    ok: bool
    status: int | None
    detail: str

    def to_dict(self) -> dict[str, object]:
        return {
            "service": self.service,
            "url": self.url,
            "ok": self.ok,
            "status": self.status,
            "detail": self.detail,
        }


def _open_direct_health(request: Request, *, timeout: float):
    """Fetch one declared health endpoint without ambient proxies or redirects.

    A remote redirect must not cause a second network request, even when a
    subsequent URL comparison would have rejected its final 200 response.
    """

    class RejectRedirect(HTTPRedirectHandler):
        def redirect_request(self, request, fp, code, msg, headers, newurl):
            return None

    return build_opener(ProxyHandler({}), RejectRedirect()).open(request, timeout=timeout)


def probe_http(name: str, url: str, *, timeout: float = 3.0) -> ProbeResult:
    """Probe one health endpoint with no proxy or redirect side effects."""

    if not math.isfinite(timeout) or timeout <= 0 or timeout > 30:
        raise ValueError("health probe timeout must be finite and within (0, 30] seconds")
    try:
        target = urlsplit(url)
        valid = (
            target.scheme in {"http", "https"}
            and target.hostname is not None
            and target.username is None
            and target.password is None
            and not target.fragment
            and target.port != 0
        )
    except ValueError:
        valid = False
    if not valid:
        return ProbeResult(
            service=name, url="", ok=False, status=None,
            detail="health probe requires HTTP(S) without credentials",
        )
    request = Request(url, headers={"User-Agent": "skeleton-app-smoke/1"})
    try:
        with _open_direct_health(request, timeout=timeout) as response:
            status = int(getattr(response, "status", 200))
            # Preserve the original URL check as a second fence even though
            # _open_direct_health already blocks redirect traversal.
            geturl = getattr(response, "geturl", None)
            effective_url = geturl() if callable(geturl) else url
            response.read(256)
        ok = 200 <= status < 300 and effective_url == url
        detail = (
            "healthy"
            if ok
            else (
                "health endpoint redirected"
                if effective_url != url
                else f"unexpected HTTP status {status}"
            )
        )
        return ProbeResult(
            service=name,
            url=url,
            ok=ok,
            status=status,
            detail=detail,
        )
    except HTTPError as exc:
        code = int(exc.code)
        return ProbeResult(
            service=name,
            url=url,
            ok=False,
            status=code,
            detail="health endpoint redirected" if 300 <= code < 400 else f"HTTP error {code}",
        )
    except (URLError, TimeoutError, OSError) as exc:
        return ProbeResult(
            service=name,
            url=url,
            ok=False,
            status=None,
            # Never include urllib exception text; a proxy/daemon can reflect
            # credentials or a sensitive target URL into the reason string.
            detail=f"{type(exc).__name__}: health endpoint unreachable",
        )



def probe_local_setup(service: ServiceSpec, *, timeout: float = 2.0) -> ProbeResult:
    """Probe the installed setup route without redirects or ambient proxies.

    Unlike a generic health probe, this is a browser-admission boundary:
    a local 302 must never cause a second request to an attacker-controlled
    URL. Only a direct 2xx response from the declared local origin counts.
    """
    from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener

    if not math.isfinite(timeout) or not 0 < timeout <= 10:
        raise ValueError("setup probe timeout must be finite and within (0, 10] seconds")
    # Reject invalid targets here as well as in the Windows launcher, so a
    # future caller cannot accidentally turn this local probe into an SSRF.
    try:
        parts = urlsplit(service.public_url)
        local = (
            parts.scheme == "http"
            and parts.hostname in {"localhost", "127.0.0.1", "::1"}
            and parts.port is not None
            and 1 <= parts.port <= 65535
            and parts.username is None
            and parts.password is None
            and parts.path in {"", "/"}
            and not parts.query
            and not parts.fragment
        )
    except ValueError:
        local = False
    if not local or service.health_path != "/setup":
        return ProbeResult(
            service=service.name, url="", ok=False, status=None,
            detail="setup probe requires a local HTTP origin and exact /setup route",
        )
    url = service.public_url.rstrip("/") + "/setup"

    class RejectRedirect(HTTPRedirectHandler):
        def redirect_request(self, request, fp, code, msg, headers, newurl):
            return None

    opener = build_opener(ProxyHandler({}), RejectRedirect())
    request = Request(url, headers={"User-Agent": "skeleton-setup-probe/1"})
    try:
        with opener.open(request, timeout=timeout) as response:
            status = int(getattr(response, "status", 200))
            effective = response.geturl()
            content_type = response.headers.get_content_type().lower()
            sample = response.read(512)
        # A local port can be occupied by a different process that returns
        # HTTP 200. Only an HTML document may admit the setup browser, never
        # a JSON health response or empty generic success payload.
        html_document = (
            content_type == "text/html"
            and sample.lstrip().lower().startswith(b"<!doctype html")
        )
        ok = 200 <= status < 300 and effective == url and html_document
        return ProbeResult(
            service=service.name, url=url, ok=ok, status=status,
            detail="healthy" if ok else "setup endpoint did not answer directly",
        )
    except HTTPError as exc:
        status = int(exc.code)
        return ProbeResult(
            service=service.name, url=url, ok=False, status=status,
            detail="health endpoint redirected" if 300 <= status < 400 else f"HTTP error {status}",
        )
    except (URLError, TimeoutError, OSError) as exc:
        return ProbeResult(
            service=service.name, url=url, ok=False, status=None,
            detail=f"{type(exc).__name__}: setup endpoint unreachable",
        )

def probe_url(service: ServiceSpec, *, timeout: float = 3.0) -> ProbeResult:
    """Probe one declared public HTTP service."""

    if not service.public_url or not service.health_path:
        return ProbeResult(
            service=service.name,
            url=service.public_url,
            ok=False,
            status=None,
            detail="no public HTTP health probe declared",
        )

    url = service.public_url.rstrip("/") + "/" + service.health_path.lstrip("/")
    return probe_http(service.name, url, timeout=timeout)

def probe_application(
    *,
    manifest: AssemblyManifest | None = None,
    full: bool = False,
    timeout: float = 3.0,
    public_url_overrides: Mapping[str, str] | None = None,
) -> tuple[ProbeResult, ...]:
    """Probe the actual host-facing URLs for the active assembly profile."""

    manifest = manifest or load_manifest()
    active = set(manifest.full_services if full else manifest.default_services)
    results = []
    for service in manifest.services:
        if service.name not in active:
            continue
        if not service.public_url or not service.health_path:
            continue
        configured_url = (public_url_overrides or {}).get(service.name)
        effective = replace(service, public_url=configured_url) if configured_url else service
        results.append(probe_url(effective, timeout=timeout))

    backend = manifest.service("backend")
    backend_url = (public_url_overrides or {}).get("backend", backend.public_url)
    ready_url = backend_url.rstrip("/") + manifest.contract_path("ready")
    results.append(probe_http("application", ready_url, timeout=timeout))
    return tuple(results)


def probes_ok(results: tuple[ProbeResult, ...]) -> bool:
    return bool(results) and all(result.ok for result in results)


def wait_for_application(
    *,
    manifest: AssemblyManifest | None = None,
    full: bool = False,
    timeout: float = 3.0,
    attempts: int = 10,
    delay: float = 1.0,
    public_url_overrides: Mapping[str, str] | None = None,
) -> tuple[ProbeResult, ...]:
    """Retry whole-application probes until healthy or the budget is exhausted."""

    if not isinstance(attempts, int) or isinstance(attempts, bool) or not 1 <= attempts <= 120:
        raise ValueError("attempts must be an integer between 1 and 120")
    if not math.isfinite(timeout) or not 0 < timeout <= 30:
        raise ValueError("timeout must be finite and within (0, 30] seconds")
    if not math.isfinite(delay) or not 0 <= delay <= 30:
        raise ValueError("delay must be finite and within [0, 30] seconds")

    manifest = manifest or load_manifest()
    latest: tuple[ProbeResult, ...] = ()
    for attempt in range(attempts):
        if public_url_overrides is None:
            latest = probe_application(manifest=manifest, full=full, timeout=timeout)
        else:
            latest = probe_application(
                manifest=manifest, full=full, timeout=timeout,
                public_url_overrides=public_url_overrides,
            )
        if probes_ok(latest):
            return latest
        if attempt + 1 < attempts and delay:
            time.sleep(delay)
    return latest
