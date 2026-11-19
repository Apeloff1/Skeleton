"""Public application assembly/bootstrap and aggregate runtime status."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import os
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from skeleton.app.assembly import load_manifest
from skeleton.app.bootstrap import public_bootstrap_payload
from core.databases import core_db
from core.product_control_runtime import public_readiness

_MANIFEST = load_manifest()
router = APIRouter(prefix=_MANIFEST.public_contract["prefix"], tags=["application"])


def _engine_internal_base() -> str:
    return os.environ.get("SKELETON_INTERNAL_URL", "http://localhost:8010").strip().rstrip("/")


async def _probe_mongo(timeout_s: float) -> dict[str, object]:
    started = time.monotonic()
    try:
        await asyncio.wait_for(core_db.command("ping"), timeout=timeout_s)
        return {
            "name": "mongo",
            "ok": True,
            "status": 200,
            "latency_ms": int((time.monotonic() - started) * 1000),
            "detail": "healthy",
        }
    except asyncio.TimeoutError:
        return {
            "name": "mongo",
            "ok": False,
            "status": None,
            "latency_ms": int((time.monotonic() - started) * 1000),
            "detail": "timeout",
        }
    except Exception as exc:
        return {
            "name": "mongo",
            "ok": False,
            "status": None,
            "latency_ms": int((time.monotonic() - started) * 1000),
            "detail": type(exc).__name__,
        }


def _probe_engine(timeout_s: float) -> dict[str, object]:
    manifest = load_manifest()
    engine = manifest.service("skeleton")
    url = _engine_internal_base() + "/" + engine.health_path.lstrip("/")
    started = time.monotonic()
    request = Request(url, headers={"User-Agent": "skeleton-app-runtime/1"})
    try:
        with urlopen(request, timeout=timeout_s) as response:
            status = int(getattr(response, "status", 200))
            body = response.read(4096)
        identity: dict[str, object] = {}
        try:
            decoded = json.loads(body.decode("utf-8"))
            candidate = decoded.get("application") if isinstance(decoded, dict) else None
            if isinstance(candidate, dict):
                identity = candidate
        except (UnicodeDecodeError, json.JSONDecodeError):
            identity = {}

        expected = {
            "name": manifest.name,
            "version": manifest.version,
            "component": "engine",
            "ingress_prefix": engine.ingress_prefix,
        }
        identity_ok = all(identity.get(key) == value for key, value in expected.items())
        ok = 200 <= status < 400 and identity_ok
        return {
            "name": "skeleton",
            "ok": ok,
            "status": status,
            "latency_ms": int((time.monotonic() - started) * 1000),
            "detail": (
                "healthy"
                if ok
                else "identity mismatch"
                if 200 <= status < 400
                else f"unexpected HTTP status {status}"
            ),
            "application": identity,
        }
    except HTTPError as exc:
        return {
            "name": "skeleton",
            "ok": False,
            "status": int(exc.code),
            "latency_ms": int((time.monotonic() - started) * 1000),
            "detail": f"HTTP error {exc.code}",
        }
    except (URLError, TimeoutError, OSError) as exc:
        return {
            "name": "skeleton",
            "ok": False,
            "status": None,
            "latency_ms": int((time.monotonic() - started) * 1000),
            "detail": f"{type(exc).__name__}: {exc}",
        }


@router.get(_MANIFEST.public_contract["bootstrap"])
def app_bootstrap() -> dict[str, object]:
    """Expose the sanitized canonical application contract to clients."""

    return public_bootstrap_payload()


async def _runtime_status(timeout_ms: int) -> dict[str, object]:
    timeout_ms = max(250, min(int(timeout_ms), 10_000))
    bootstrap = public_bootstrap_payload()
    timeout_s = timeout_ms / 1000.0
    engine, mongo = await asyncio.gather(
        asyncio.to_thread(_probe_engine, timeout_s),
        _probe_mongo(timeout_s),
    )
    services = [
        {
            "name": "backend",
            "ok": True,
            "status": 200,
            "latency_ms": 0,
            "detail": "healthy",
        },
        engine,
        mongo,
    ]
    product_readiness: dict[str, object]
    try:
        report = public_readiness()
        product_readiness = {
            "available": True,
            "canonical_actions": int(report.get("canonical_actions", 0)),
            "ready_actions": int(report.get("ready_actions", 0)),
            "ready_pct": float(report.get("ready_pct", 0.0)),
            "governed_unbound": int(report.get("governed_unbound", 0)),
            "unsafe_actions": int(report.get("unsafe_actions", 0)),
            "policy_gaps": int(report.get("policy_gaps", 0)),
            "attestation_sha256": str(report.get("attestation_sha256", "")),
        }
    except Exception as exc:
        product_readiness = {
            "available": False,
            "canonical_actions": 0,
            "ready_actions": 0,
            "ready_pct": 0.0,
            "governed_unbound": 0,
            "unsafe_actions": 0,
            "policy_gaps": 0,
            "attestation_sha256": "",
            "detail": type(exc).__name__,
        }

    return {
        "ok": all(bool(item["ok"]) for item in services),
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "application": bootstrap["application"],
        "contract": bootstrap["contract"],
        "scope": "public-runtime",
        "services": services,
        "product": product_readiness,
    }


@router.get(_MANIFEST.public_contract["status"])
async def app_status(timeout_ms: int = 2500) -> dict[str, object]:
    """Aggregate the public application runtime behind one backend contract."""

    return await _runtime_status(timeout_ms)


@router.get(_MANIFEST.public_contract["ready"])
async def app_ready(timeout_ms: int = 2500) -> JSONResponse:
    """Return a fail-closed readiness verdict for the assembled application."""

    payload = await _runtime_status(timeout_ms)
    return JSONResponse(status_code=200 if payload["ok"] else 503, content=payload)
