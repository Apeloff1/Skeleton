"""HTTP smoke probes for the assembled application."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable, Mapping
import math
import re
import time
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from skeleton.app.assembly import AssemblyManifest, ServiceSpec, load_manifest
from skeleton.app.install_http_transport import DirectHTTPHandler, DirectHTTPSHandler


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

    return build_opener(ProxyHandler({}), RejectRedirect(),
                        DirectHTTPHandler(), DirectHTTPSHandler()).open(request, timeout=timeout)


def _response_metadata(response) -> tuple[int, str] | None:
    """Never coerce or default an unobserved transport status or URL."""
    status = getattr(response, "status", None)
    geturl = getattr(response, "geturl", None)
    if type(status) is not int or not 100 <= status <= 599 or not callable(geturl):
        return None
    effective = geturl()
    if not isinstance(effective, str) or not effective:
        return None
    return status, effective


def _http_error_status(error: HTTPError) -> int | None:
    # HTTPError is also a file-like response. Close it even when malformed;
    # repeated cold-start retries must not accumulate open error responses.
    try:
        status = error.code
        return status if type(status) is int and 100 <= status <= 599 else None
    finally:
        try:
            error.close()
        except (OSError, HTTPException, ValueError):
            pass


def probe_http(name: str, url: str, *, timeout: float = 3.0) -> ProbeResult:
    """Probe one health endpoint with no proxy or redirect side effects."""

    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 < timeout <= 30 or not math.isfinite(timeout):
        raise ValueError("health probe timeout must be finite and within (0, 30] seconds")
    try:
        # Reject non-string and whitespace/control characters before urllib parsing.
        # urllib strips some control bytes, which can change the actual target.
        if (not isinstance(url, str) or not url or len(url) > 4096
                or any(ord(ch) <= 32 or ord(ch) == 127 for ch in url)
                or "?" in url or "#" in url):
            raise ValueError("invalid health target characters")
        target = urlsplit(url)
        valid = (
            target.scheme in {"http", "https"}
            and target.hostname is not None
            and target.hostname != ""
            # Reject ambiguous authority delimiters before urllib transport.
            and "\\" not in target.netloc
            and "%" not in target.netloc
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
            # A missing or malformed transport status is never an implicit 200.
            # The final URL must be supplied by the transport, not assumed.
            metadata = _response_metadata(response)
            if metadata is None:
                return ProbeResult(
                    service=name, url=url, ok=False, status=None,
                    detail="health transport returned invalid response metadata",
                )
            status, effective_url = metadata
            # Liveness is a status-only contract. Do not read a potentially
            # slow or unbounded body; strict product readiness is separate.
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
        code = _http_error_status(exc)
        return ProbeResult(
            service=name,
            url=url,
            ok=False,
            status=code,
            detail=("health transport returned invalid response metadata" if code is None
                    else "health endpoint redirected" if 300 <= code < 400 else f"HTTP error {code}"),
        )
    except (URLError, TimeoutError, OSError, HTTPException, ValueError, UnicodeError) as exc:
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
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not 0 < timeout <= 10
        or not math.isfinite(timeout)
    ):
        raise ValueError("setup probe timeout must be finite and within (0, 10] seconds")
    # Reject invalid targets here as well as in the Windows launcher, so a
    # future caller cannot accidentally turn this local probe into an SSRF.
    try:
        # urllib can silently strip controls from a URL. Reject before parsing
        # to prevent a malformed setup origin from becoming a different target.
        if (
            not isinstance(service.public_url, str)
            or not service.public_url
            or len(service.public_url) > 4096
            or any(ord(ch) <= 32 or ord(ch) == 127 for ch in service.public_url)
            or any(ch in service.public_url for ch in ("?", "#", "%", chr(92)))
        ):
            raise ValueError("invalid setup origin")
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

    request = Request(url, headers={"User-Agent": "skeleton-setup-probe/1"})
    try:
        with _open_direct_health(request, timeout=timeout) as response:
            metadata = _response_metadata(response)
            if metadata is None:
                return ProbeResult(service.name, url, False, None,
                                   "setup transport returned invalid response metadata")
            status, effective = metadata
            if not 200 <= status < 300 or effective != url:
                return ProbeResult(service.name, url, False, status,
                                   "setup endpoint did not answer directly")
            headers = getattr(response, "headers", None)
            content_types = getattr(headers, "get_all", None)
            get_content_type = getattr(headers, "get_content_type", None)
            if not callable(content_types) or not callable(get_content_type):
                return ProbeResult(service.name, url, False, status,
                                   "setup transport returned invalid content metadata")
            values = content_types("Content-Type")
            if (not isinstance(values, list) or len(values) != 1
                    or not isinstance(values[0], str)
                    or get_content_type() != "text/html"):
                return ProbeResult(service.name, url, False, status,
                                   "setup endpoint did not answer directly")
            sample = response.read(512)
        # A local port can be occupied by a different process that returns
        # HTTP 200. Only an HTML document may admit the setup browser, never
        # a JSON health response or empty generic success payload.
        html_document = (
            isinstance(sample, bytes)
            and len(sample) <= 512
            and re.match(rb"\s*<!doctype\s+html\s*>", sample, re.IGNORECASE) is not None
        )
        ok = 200 <= status < 300 and effective == url and html_document
        return ProbeResult(
            service=service.name, url=url, ok=ok, status=status,
            detail="healthy" if ok else "setup endpoint did not answer directly",
        )
    except HTTPError as exc:
        status = _http_error_status(exc)
        return ProbeResult(
            service=service.name, url=url, ok=False, status=status,
            detail=("setup transport returned invalid response metadata" if status is None
                    else "health endpoint redirected" if 300 <= status < 400 else f"HTTP error {status}"),
        )
    except (URLError, TimeoutError, OSError, HTTPException, ValueError, UnicodeError) as exc:
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

def _admitted(admit: Callable[[], bool] | None) -> bool:
    if admit is None:
        return True
    try:
        return admit() is True
    except (OSError, ValueError, RuntimeError, UnicodeError):
        return False


def probe_application(
    *,
    manifest: AssemblyManifest | None = None,
    full: bool = False,
    timeout: float = 3.0,
    public_url_overrides: Mapping[str, str] | None = None,
    admit: Callable[[], bool] | None = None,
) -> tuple[ProbeResult, ...]:
    """Probe the actual host-facing URLs for the active assembly profile."""

    manifest = manifest or load_manifest()
    if not _admitted(admit):
        return ()
    active = set(manifest.full_services if full else manifest.default_services)
    results = []
    for service in manifest.services:
        if service.name not in active:
            continue
        if not service.public_url or not service.health_path:
            continue
        configured_url = (public_url_overrides or {}).get(service.name)
        effective = replace(service, public_url=configured_url) if configured_url else service
        if not _admitted(admit):
            return ()
        results.append(probe_url(effective, timeout=timeout))
        if not _admitted(admit):
            return ()

    backend = manifest.service("backend")
    backend_url = (public_url_overrides or {}).get("backend", backend.public_url)
    ready_url = backend_url.rstrip("/") + manifest.contract_path("ready")
    if not _admitted(admit):
        return ()
    results.append(probe_http("application", ready_url, timeout=timeout))
    return tuple(results) if _admitted(admit) else ()


def readiness_targets(
    manifest: AssemblyManifest, *, full: bool=False,
    public_url_overrides: Mapping[str,str] | None=None,
) -> dict[str,str]:
    """Exact expected health evidence, excluding the non-HTTP Mongo service."""
    if type(full) is not bool:
        raise ValueError("readiness profile must be explicit")
    overrides = public_url_overrides or {}
    roles = {"frontend", "backend", "skeleton"}
    if full:
        roles.add("chroma")
    active = set(manifest.full_services if full else manifest.default_services)
    if not roles.issubset(active) or set(overrides).difference(manifest.service_names):
        raise ValueError("readiness service inventory invalid")
    targets = {}
    for role in sorted(roles):
        service = manifest.service(role)
        origin = overrides.get(role, service.public_url)
        if type(origin) is not str or not origin or not service.health_path:
            raise ValueError("readiness endpoint missing")
        targets[role] = origin.rstrip("/") + "/" + service.health_path.lstrip("/")
    backend = overrides.get("backend", manifest.service("backend").public_url)
    targets["application"] = backend.rstrip("/") + manifest.contract_path("ready")
    if len(set(targets.values())) != len(targets):
        raise ValueError("readiness endpoint collision")
    return targets


def probes_ok(results: tuple[ProbeResult, ...], *, manifest: AssemblyManifest | None=None,
              full: bool=False, public_url_overrides: Mapping[str,str] | None=None) -> bool:
    """Admit complete, one-to-one, exact-URL positive HTTP evidence.

    No caller may promote a partial list, duplicate role, different port,
    fabricated truthy flag or missing status to whole-application readiness.
    This is liveness/readiness transport evidence, not AI or device proof.
    """
    try:
        expected = readiness_targets(manifest or load_manifest(),full=full,
                                     public_url_overrides=public_url_overrides)
        if type(results) not in (tuple,list) or len(results) != len(expected):
            return False
        seen = set()
        for row in results:
            if (type(row) is not ProbeResult or type(row.service) is not str
                    or row.service not in expected or row.service in seen
                    or row.url != expected[row.service] or row.ok is not True
                    or type(row.status) is not int or not 200 <= row.status < 300):
                return False
            seen.add(row.service)
        return seen == set(expected)
    except (OSError,ValueError,KeyError,TypeError,AttributeError):
        return False


def wait_for_application(
    *,
    manifest: AssemblyManifest | None = None,
    full: bool = False,
    timeout: float = 3.0,
    attempts: int = 10,
    delay: float = 1.0,
    public_url_overrides: Mapping[str, str] | None = None,
    admit: Callable[[], bool] | None = None,
) -> tuple[ProbeResult, ...]:
    """Retry whole-application probes until healthy or the budget is exhausted."""

    if not isinstance(attempts, int) or isinstance(attempts, bool) or not 1 <= attempts <= 120:
        raise ValueError("attempts must be an integer between 1 and 120")
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 < timeout <= 30 or not math.isfinite(timeout):
        raise ValueError("timeout must be finite and within (0, 30] seconds")
    if isinstance(delay, bool) or not isinstance(delay, (int, float)) or not 0 <= delay <= 30 or not math.isfinite(delay):
        raise ValueError("delay must be finite and within [0, 30] seconds")

    manifest = manifest or load_manifest()
    latest: tuple[ProbeResult, ...] = ()
    # Latch a refused epoch across the complete retry campaign. No subsequent
    # successful observation can rehabilitate evidence collected across it.
    valid = True

    def still_admitted():
        nonlocal valid
        valid = valid and _admitted(admit)
        return valid

    for attempt in range(attempts):
        if not still_admitted():
            return ()
        options = {}
        if public_url_overrides is not None:
            options["public_url_overrides"] = public_url_overrides
        if admit is not None:
            options["admit"] = still_admitted
        latest = probe_application(manifest=manifest, full=full, timeout=timeout, **options)
        if not still_admitted():
            return ()
        if probes_ok(latest,manifest=manifest,full=full,public_url_overrides=public_url_overrides):
            return latest
        if attempt + 1 < attempts and delay:
            time.sleep(delay)
    return latest if still_admitted() else ()
