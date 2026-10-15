"""HTTP smoke probes for the assembled application."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

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


def probe_http(name: str, url: str, *, timeout: float = 3.0) -> ProbeResult:
    """Probe one HTTP endpoint without external client dependencies."""

    request = Request(url, headers={"User-Agent": "skeleton-app-smoke/1"})
    try:
        with urlopen(request, timeout=timeout) as response:
            status = int(getattr(response, "status", 200))
            # urllib automatically follows redirects. A redirected login page
            # returning 200 is NOT evidence the declared health endpoint works.
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
        return ProbeResult(
            service=name,
            url=url,
            ok=False,
            status=int(exc.code),
            detail=f"HTTP error {exc.code}",
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


def probe_url(service: ServiceSpec, *, timeout: float = 3.0) -> ProbeResult:
    """Probe one declared public HTTP service."""

    if not service.public_url or not service.health_path:
        return ProbeResult(
            service=service.name,
            url=service.public_url,
            ok=True,
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

    if attempts < 1:
        raise ValueError("attempts must be at least one")
    if timeout <= 0:
        raise ValueError("timeout must be greater than zero")
    if delay < 0:
        raise ValueError("delay must not be negative")

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
