"""Read-only first-install diagnostics for the existing application assembly.

Configuration is not inference evidence. Live AI availability is read only
from the canonical application endpoint; this module never creates a provider,
loads model weights, starts a crawler or submits application work.
"""

from __future__ import annotations

import math
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


def _bounded_json(url: str, *, timeout: float) -> dict[str, object] | None:
    from skeleton.app.studio_readiness import _bounded_server

    parts = urlsplit(url)
    if parts.query or parts.fragment:
        return None
    result = _bounded_server(
        Path(__file__).resolve().parents[2],
        f"{parts.scheme}://{parts.netloc}",
        None,
        timeout,
        endpoint=parts.path or "/",
        schema=None,
        max_response_bytes=65536,
    )
    value = result.get("report") if result.get("observed") is True else None
    return value if isinstance(value, dict) else None


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
    status = _bounded_json(backend_base.rstrip("/") + "/api/health/registry", timeout=timeout)
    critical = status.get("critical_routes") if isinstance(status, dict) else None
    if (
        isinstance(critical, dict)
        and type(critical.get("ok")) is bool
        and type(critical.get("report_available")) is bool
        and isinstance(critical.get("missing"), list)
        and all(isinstance(item, str) and len(item) <= 128 for item in critical["missing"])
        and len(critical["missing"]) <= 32
    ):
        report.update(
            observed=critical["report_available"],
            ready=critical["ok"] and critical["report_available"],
            missing=critical["missing"],
        )
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
    host = inspect_host(root)
    checks = preflight(root, runtime=True, environ=environ)
    values = _runtime_env(root, environ)
    manifest = load_manifest()
    try:
        manifest = runtime_manifest(manifest, root=root, environ=values)
    except ValueError:
        # The original port failure is already an explicit preflight finding.
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
    if live:
        from skeleton.app.health import probe_application, probes_ok

        probes = probe_application(manifest=manifest, timeout=timeout)
        services_ready = probes_ok(probes)
        live_checks = [probe.to_dict() for probe in probes]
        backend_base = manifest.service("backend").public_url.rstrip("/")
        route_registry = critical_backend_route_report(backend_base, timeout=timeout)
        services_ready = bool(services_ready) and route_registry["ready"] is True
        status_url = backend_base + "/api/ai/providers"
        status = _bounded_json(status_url, timeout=timeout)
        if (
            status is not None
            and status.get("engine") == "skeleton-engine"
            and isinstance(status.get("providers"), list)
            and type(status.get("llm_available")) is bool
            and status.get("availability_observed") is True
        ):
            ai.update(
                available=status["llm_available"],
                observed=True,
                scope="Canonical AI readiness projection; no inference or model quality claim.",
            )
        else:
            ai["scope"] = (
                "Canonical AI readiness could not be observed; configuration does not establish availability."
            )

    next_steps = []
    if not host.ready:
        next_steps.extend(
            check.remediation
            for check in host.checks
            if check.required and not check.ok and check.remediation
        )
    if not checks_ok(checks):
        next_steps.append(
            "Run python -m skeleton app setup, then python -m skeleton app check --runtime; preserve the private .env file."
        )
    if not live:
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
    if not configured or ai["available"] is False:
        next_steps.append(
            "Configure genuine trained local weights or the engine-owned hosted provider in .env; see docs/APP_ASSEMBLY.md. Restart the engine after changes."
        )
    elif live and ai["observed"] is not True:
        next_steps.append(
            "AI configuration is present but canonical readiness was not observed. Inspect app logs backend and app logs skeleton, then rerun app doctor --live; do not treat configuration alone as model availability."
        )
    report = {
        "schema_version": "skeleton.application.first_install_report.v1",
        "platform_ready": host.ready,
        "configuration_ready": checks_ok(checks),
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

        report["studio"] = studio_readiness_report(
            root,
            values=values,
            backend_url=manifest.service("backend").public_url,
            live=live,
            timeout=timeout,
            auth_token_file=auth_token_file,
        )
        crawler = report["studio"]["server"]["crawler"]
        observed = crawler.get("report", {})
        if (
            crawler.get("observed") is True
            and type(observed.get("available")) is bool
            and type(observed.get("configured")) is bool
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
    return report
