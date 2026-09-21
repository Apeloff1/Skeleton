"""HTTP smoke probes for the assembled application."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
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


def probe_url(service: ServiceSpec, *, timeout: float = 3.0) -> ProbeResult:
    """Probe one public HTTP service without external client dependencies."""

    if not service.public_url or not service.health_path:
        return ProbeResult(
            service=service.name,
            url=service.public_url,
            ok=True,
            status=None,
            detail="no public HTTP health probe declared",
        )

    url = service.public_url.rstrip("/") + "/" + service.health_path.lstrip("/")
    request = Request(url, headers={"User-Agent": "skeleton-app-smoke/1"})
    try:
        with urlopen(request, timeout=timeout) as response:
            status = int(getattr(response, "status", 200))
            response.read(256)
        ok = 200 <= status < 400
        return ProbeResult(
            service=service.name,
            url=url,
            ok=ok,
            status=status,
            detail="healthy" if ok else f"unexpected HTTP status {status}",
        )
    except HTTPError as exc:
        return ProbeResult(
            service=service.name,
            url=url,
            ok=False,
            status=int(exc.code),
            detail=f"HTTP error {exc.code}",
        )
    except (URLError, TimeoutError, OSError) as exc:
        return ProbeResult(
            service=service.name,
            url=url,
            ok=False,
            status=None,
            detail=f"{type(exc).__name__}: {exc}",
        )


def probe_application(
    *,
    manifest: AssemblyManifest | None = None,
    full: bool = False,
    timeout: float = 3.0,
) -> tuple[ProbeResult, ...]:
    """Probe the public surfaces for the active assembly profile."""

    manifest = manifest or load_manifest()
    active = set(manifest.full_services if full else manifest.default_services)
    results = []
    for service in manifest.services:
        if service.name not in active:
            continue
        if not service.public_url or not service.health_path:
            continue
        results.append(probe_url(service, timeout=timeout))
    return tuple(results)


def probes_ok(results: tuple[ProbeResult, ...]) -> bool:
    return bool(results) and all(result.ok for result in results)
