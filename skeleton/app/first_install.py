"""Read-only first-install diagnostics for the existing application assembly.

Configuration is not inference evidence. Live AI availability is read only
from the canonical application endpoint; this module never creates a provider,
loads model weights, starts a crawler or submits application work.
"""

from __future__ import annotations

import math
import os
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlsplit

from skeleton.app.assembly import (
    _runtime_env,
    _usable_secret,
    checks_ok,
    find_repo_root,
    load_manifest,
    preflight,
    runtime_manifest,
)
from skeleton.app.preloader import inspect_host
from skeleton.app.setup_runtime import runtime_source_fingerprint


def _configuration_epoch(root: Path) -> str | None:
    """Distinguish an absent source from a linked, mutated or unreadable one."""
    try:
        (root / ".env").lstat()
    except FileNotFoundError:
        return None
    return runtime_source_fingerprint(root)


def _bounded_json(
    url: str, *, timeout: float, max_response_bytes: int = 65536,
) -> dict[str, object] | None:
    from skeleton.app.studio_readiness import _bounded_server

    try:
        if (type(url) is not str or not 1 <= len(url) <= 4096
                or any(ord(ch) <= 32 or ord(ch) == 127 for ch in url)
                or any(ch in url for ch in ("?", "#", chr(92)))):
            return None
        parts = urlsplit(url)
        if (parts.scheme not in {"http", "https"} or not parts.hostname
                or parts.username is not None or parts.password is not None
                or parts.query or parts.fragment or "%" in parts.netloc
                or parts.port == 0):
            return None
    except ValueError:
        return None
    result = _bounded_server(
        Path(__file__).resolve().parents[2],
        f"{parts.scheme}://{parts.netloc}",
        None,
        timeout,
        endpoint=parts.path or "/",
        schema=None,
        max_response_bytes=max_response_bytes,
    )
    value = result.get("report") if result.get("observed") is True else None
    return value if isinstance(value, dict) else None


# Mirrored public contract, not a backend import: standalone installer
# distributions must not initialize FastAPI or its dependencies. A source
# contract test requires parity with backend/routes/registry_health.py.
CRITICAL_ROUTE_PATHS = {
    "routes.creator_economy": "/api/creators",
    "routes.git_operations": "/api/git/status",
    "routes.jeeves_media": "/api/jeeves/media/types",
    "routes.lafs": "/api/lafs/stats",
    "routes.marketplace": "/api/marketplace/listings",
    "routes.sorting_vault": "/api/sorting-vault/connections",
    "routes.swarm_cold_legion": "/api/galaxy-studio/swarm/cold/stats",
    "routes.swarm_hub": "/api/galaxy-studio/swarm/agents",
}


def critical_route_evidence(status: object) -> tuple[bool, bool, list[str]]:
    """Validate the redacted registry summary against positive mount evidence.

    Only known first-party module identities leave this boundary. Incomplete
    or contradictory mount inventories can never establish readiness.
    """
    if type(status) is not dict:
        return False, False, []
    critical = status.get("critical_routes")
    if type(critical) is not dict:
        return False, False, []
    reported = critical.get("missing")
    if (type(critical.get("ok")) is not bool
            or type(critical.get("report_available")) is not bool
            or type(reported) is not list or len(reported) > len(CRITICAL_ROUTE_PATHS)
            or any(type(name) is not str or name not in CRITICAL_ROUTE_PATHS for name in reported)
            or len(set(reported)) != len(reported)):
        return False, False, []
    if not critical["report_available"]:
        return False, False, sorted(reported)
    names = status.get("mounted_names")
    paths = status.get("mounted_paths")
    if (type(names) is not list or len(names) > 16384
            or any(type(name) is not str for name in names)
            or type(paths) is not dict or len(paths) > 16384):
        return False, False, []
    mounted = set(names)
    missing = set(reported)
    for module, endpoint in CRITICAL_ROUTE_PATHS.items():
        entries = paths.get(module)
        if (module not in mounted or type(entries) is not list or len(entries) > 16384
                or any(type(path) is not str for path in entries) or endpoint not in entries):
            missing.add(module)
    return True, not missing and critical["ok"], sorted(missing)


def critical_backend_route_report(backend_base: str, *, timeout: float = 3.0) -> dict[str, object]:
    """Fail-closed live check shared by app doctor and install --start.

    A 200 from /health does not prove first-party application endpoints mounted.
    Only a bounded, unredirected live backend report can prove their presence.
    """
    report: dict[str, object] = {
        "observed": False,
        "ready": False,
        "missing": [],
        "scope": "Critical first-party route registration must be observed from the live backend.",
    }
    # The registry includes the mounted route inventory, which exceeds 64 KiB
    # on a complete installation. Keep the larger allowance local to this
    # endpoint; ordinary readiness projections retain their smaller bound.
    if type(backend_base) is not str or not backend_base:
        return report
    status = _bounded_json(
        backend_base.rstrip("/") + "/api/health/registry",
        timeout=timeout, max_response_bytes=512 * 1024,
    )
    observed, ready, missing = critical_route_evidence(status)
    report.update(observed=observed, ready=ready, missing=missing)
    return report


def first_install_report(
    root: Path | None = None,
    *,
    live: bool = False,
    timeout: float = 3.0,
    environ: Mapping[str, str] | None = None,
    studio: bool = False,
    auth_token_file: Path | None = None,
) -> dict[str, object]:
    """Return bounded, redacted host/configuration and optional live findings."""

    if type(live) is not bool:
        raise TypeError("live inspection must be an explicit boolean")
    if type(studio) is not bool:
        raise TypeError("studio inspection must be an explicit boolean")
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not math.isfinite(timeout)
        or not 0 < timeout <= 10
    ):
        raise ValueError("doctor timeout must be finite and greater than zero, at most 10 seconds")
    if auth_token_file is not None and not (studio and live):
        raise ValueError("--auth-token-file requires --studio --live")
    root = (root or find_repo_root()).resolve()
    # Freeze process overrides before the first read. A report must not
    # combine one provider selection with another set of public ports.
    captured = dict(os.environ if environ is None else environ)
    host = inspect_host(root)
    try:
        initial_epoch = _configuration_epoch(root)
        epoch_admitted = True
    except (OSError, ValueError, UnicodeError):
        initial_epoch = None
        epoch_admitted = False

    def epoch_stable():
        nonlocal epoch_admitted
        if not epoch_admitted:
            return False
        try:
            epoch_admitted = _configuration_epoch(root) == initial_epoch
        except (OSError, ValueError, UnicodeError):
            epoch_admitted = False
        return epoch_admitted

    checks = preflight(root, runtime=True, environ=captured)
    try:
        if not epoch_stable():
            raise ValueError("runtime source not admitted")
        values = _runtime_env(root, captured)
        if not epoch_stable():
            raise ValueError("runtime source changed")
    except (OSError, ValueError, UnicodeError):
        # An unsafe credential source is not readable configuration evidence.
        # Preserve the original in place for manual recovery, and do not make
        # network requests that might otherwise be attributed to stale values.
        values = {}
        source_ok = False
        live = False
    else:
        source_ok = True
    manifest = load_manifest()
    manifest_ok = False
    if source_ok:
        try:
            manifest = runtime_manifest(manifest, root=root, environ=captured)
            manifest_ok = True
        except (OSError, ValueError, UnicodeError):
            live = False
    if not epoch_stable():
        source_ok = False
        values = {}
        live = False
    provider = values.get("AI_PROVIDER", "local").strip().lower() or "local"
    provider = provider if provider in {"local", "openai"} else "unsupported"
    local_paths = [values.get(key, "").strip() for key in (
        "AI_LOCAL_MODEL_PATH", "AI_LOCAL_DEPLOYMENT_PATH", "AI_LOCAL_MODEL_CATALOG_PATH",
    )]
    configured = (
        sum(bool(path) for path in local_paths) == 1
        if provider == "local"
        else (
            any(_usable_secret(values.get(key, "")) for key in ("OPENAI_API_KEY", "EMERGENT_LLM_KEY"))
            if provider == "openai"
            else False
        )
    )
    ai: dict[str, object] = {
        "provider": provider,
        "configuration": "configured" if configured else "unconfigured",
        "available": None,
        "observed": False,
        "scope": "Configuration only; no model execution or quality measurement performed.",
    }
    if provider == "local":
        configured_paths = sum(bool(path) for path in local_paths)
        ai["configuration_valid"] = configured_paths == 1
        ai["configuration_code"] = (
            "local_configuration_invalid" if configured_paths > 1
            else "local_model_not_configured" if configured_paths == 0
            else "local_model_catalog_configured" if local_paths[2]
            else "local_model_configured"
        )
        ai["catalog_configured"] = bool(local_paths[2])
    services_ready = None
    route_registry = {
        "observed": False,
        "ready": False,
        "missing": [],
        "scope": "Critical first-party route registration must be observed from the live backend.",
    }
    live_checks: list[dict[str, object]] = []
    if live and source_ok and manifest_ok:
        from skeleton.app.health import probe_application, probes_ok

        probes = probe_application(manifest=manifest, timeout=timeout)
        services_ready = probes_ok(probes)
        live_checks = [probe.to_dict() for probe in probes]
        backend_base = manifest.service("backend").public_url.rstrip("/")
        if epoch_stable():
            route_registry = critical_backend_route_report(backend_base, timeout=timeout)
        services_ready = bool(services_ready) and route_registry["ready"] is True
        status_url = backend_base + "/api/ai/providers"
        status = _bounded_json(status_url, timeout=timeout) if epoch_stable() else None
        if (
            status is not None
            and status.get("engine") == "skeleton-engine"
            and isinstance(status.get("providers"), list)
            and len(status["providers"]) <= 32
            and all(type(name) is str and 0 < len(name) <= 64
                    for name in status["providers"])
            and len(set(status["providers"])) == len(status["providers"])
            # The active provider must actually exist in the canonical
            # advertised inventory; an inconsistent response cannot attest
            # configured local or hosted model availability.
            and provider in status["providers"]
            and type(status.get("llm_available")) is bool
            and status.get("availability_observed") is True
            # A healthy *different* provider must never certify the selected
            # provider. The active provider is an exact canonical identity.
            and status.get("active") == provider
            and configured
        ):
            ai.update(
                available=status["llm_available"],
                observed=True,
                scope="Canonical AI readiness projection; no inference or model quality claim.",
            )
            code = status.get("active_readiness_code")
            if (provider == "local" and status["llm_available"] is False
                    and status.get("active") == "local" and isinstance(code, str)
                    and code in {"local_guard_unavailable", "local_guard_configuration_invalid"}):
                ai["readiness_code"] = code
        else:
            ai["scope"] = (
                "Canonical AI readiness could not be observed; configuration does not establish availability."
            )

    def clear_epoch_observations():
        # Do not leave a previously healthy provider or a mounted route list
        # in a receipt whose admitted configuration no longer exists.
        ai.update(provider="unsupported", configuration="unobserved",
                  available=None, observed=False,
                  scope="Runtime configuration changed or became unsafe; no live evidence retained.")
        for key in ("readiness_code", "configuration_valid", "configuration_code",
                    "catalog_configured"):
            ai.pop(key, None)
        route_registry.update(observed=False, ready=False, missing=[])
        live_checks.clear()

    if not epoch_stable():
        source_ok = False
        configured = False
        live = False
        services_ready = None
        clear_epoch_observations()

    configuration_ready = bool(source_ok and manifest_ok and checks_ok(checks))
    next_steps = []
    if not host.ready:
        next_steps.extend(
            check.remediation
            for check in host.checks
            if check.required and not check.ok and check.remediation
        )
    if not source_ok:
        next_steps.append(
            "The private runtime .env is unsafe or unreadable. Preserve the original; "
            "repair its file type, size, ownership or links before retrying setup. "
            "Do not replace stored database credentials automatically."
        )
    elif not configuration_ready:
        next_steps.append(
            "Run python -m skeleton app setup, then python -m skeleton app check --runtime; preserve the private .env file."
        )
    if not live and source_ok:
        next_steps.append(
            "Start the existing services with python -m skeleton app up, then rerun app doctor --live."
        )
    elif services_ready is False:
        next_steps.append(
            "Inspect python -m skeleton app ps and app logs <service>; service startup has not converged."
        )
    if live and route_registry["ready"] is not True:
        next_steps.append(
            "Inspect backend /api/health/registry critical_routes and backend boot logs; required application routes are missing or unverified."
        )
    if ai.get("readiness_code") == "local_guard_unavailable":
        next_steps.append(
            "The required trusted local AI guard is unavailable. Preparing or replacing model weights alone will not enable local chat; see docs/qa/GUARDED_LOCAL_READINESS_2026-10-28.md."
        )
    elif ai.get("readiness_code") == "local_guard_configuration_invalid":
        next_steps.append(
            "The required local AI guard configuration is invalid. Review the engine configuration and docs/qa/GUARDED_LOCAL_READINESS_2026-10-28.md; do not disable the guard."
        )
    if source_ok and (not configured or (ai["available"] is False and "readiness_code" not in ai)):
        next_steps.append(
            "Configure genuine trained local weights or the engine-owned hosted provider in .env; see docs/APP_ASSEMBLY.md. Restart the engine after changes."
        )
    elif live and ai["observed"] is not True:
        next_steps.append(
            "AI configuration is present but canonical readiness was not observed. Inspect app logs backend and app logs skeleton, then rerun app doctor --live; do not treat configuration alone as model availability."
        )
    # Service/route readiness is deliberately not AI readiness. A healthy
    # app shell may be useful while a guard is blocked, but never qualify AI.
    ai_ready = (host.ready is True and configuration_ready
                and services_ready is True and ai["observed"] is True
                and ai["available"] is True and configured)
    report = {
        "schema_version": "skeleton.application.first_install_report.v1",
        "ai_ready": ai_ready,
        "ai_ready_scope": "Observed provider availability only; not inference, quality, device or release qualification.",
        "platform_ready": host.ready,
        "configuration_ready": configuration_ready,
        "services_ready": services_ready,
        "critical_routes": route_registry,
        "ai": ai,
        "crawler": {
            "available": None,
            "observed": False,
            "authentication_required": True,
            "readiness_path": "/api/dragon-academy/crawler/readiness",
            "scope": "Sign in to inspect canonical Mongo/engine admission; doctor never creates a crawl session.",
        },
        "checks": {
            "host": [check.to_dict() for check in host.checks],
            "configuration": [check.to_dict() for check in checks],
            "live": live_checks,
        },
        "endpoints": {
            "product": manifest.service("frontend").public_url.rstrip("/") + "/product",
            "backend": manifest.service("backend").public_url,
            "engine": manifest.service("skeleton").public_url,
        },
        "next_steps": list(dict.fromkeys(next_steps)),
    }
    if studio:
        from skeleton.app.studio_readiness import studio_readiness_report

        # Recheck immediately before a token can leave the process.
        studio_live = live and epoch_stable()
        report["studio"] = studio_readiness_report(
            root,
            values=values,
            backend_url=manifest.service("backend").public_url,
            live=studio_live,
            timeout=timeout,
            # Unsafe .env or invalid port configuration disables live
            # inspection; never pass an authenticated token to a downgraded
            # diagnostics call that cannot bind its target.
            auth_token_file=auth_token_file if studio_live else None,
            admit_live=epoch_stable,
        )
        crawler = report["studio"]["server"]["crawler"]
        observed = crawler.get("report", {})
        if (
            crawler.get("observed") is True
            and type(observed.get("available")) is bool
            and type(observed.get("configured")) is bool
            and type(observed.get("code")) is str
            and observed["code"] in {
                "ready", "crawler_storage_unavailable", "crawler_admission_unconfigured",
                "crawler_admission_unreachable", "crawler_runtime_unavailable",
                "crawler_indexes_unavailable",
            }
            and (not observed["available"] or observed["configured"])
            and (observed["code"] == "ready") == observed["available"]
        ):
            report["crawler"].update(
                available=observed["available"],
                configured=observed["configured"],
                observed=True,
                code=observed.get("code"),
                scope="Authenticated canonical crawler readiness; no capture or training requested.",
            )
            if not observed["available"]:
                report["next_steps"].append(
                    "Inspect the authenticated crawler readiness report; configure its existing Mongo storage and canonical engine admission before starting capture."
                )
    if not epoch_stable():
        # Covers mutations during authenticated studio/crawler probes as well
        # as final report construction. Retain no stale runtime evidence.
        clear_epoch_observations()
        report.update(configuration_ready=False, services_ready=None, ai_ready=False)
        report["checks"]["live"] = []
        report["endpoints"] = {}
        report["next_steps"] = [item for item in report["next_steps"]
                                if "app up" not in item and "Configure genuine trained" not in item]
        report["crawler"].update(available=None, observed=False,
                                 scope="Runtime configuration changed; crawler not observed.")
        report["crawler"].pop("configured", None)
        report["crawler"].pop("code", None)
        if studio:
            denied = {"observed": False, "code": "runtime_configuration_changed"}
            report["studio"]["server"] = {
                **denied, "dragon_runtime": dict(denied), "crawler": dict(denied),
            }
        step = ("Runtime configuration changed or is unsafe; preserve the private .env "
                "and rerun diagnostics before trusting any service observation.")
        if step not in report["next_steps"]:
            report["next_steps"].append(step)
    return report
