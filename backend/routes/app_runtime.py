"""Public application assembly/bootstrap and aggregate runtime status."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import math
import os
import re
import time
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Request
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


async def _probe_engine(timeout_s: float) -> dict[str, object]:
    manifest = load_manifest()
    engine = manifest.service("skeleton")
    url = _engine_internal_base() + "/" + engine.health_path.lstrip("/")
    started = time.monotonic()
    status = None
    identity: dict[str, object] = {}

    def finite_number(value: str) -> float:
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("nonfinite health response")
        return number

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate health field")
            result[key] = value
        return result

    def reject_constant(value):
        raise ValueError("nonfinite health response")

    def finding(ok: bool, detail: str) -> dict[str, object]:
        return {
            "name": "skeleton",
            "ok": ok,
            "status": status,
            "latency_ms": int((time.monotonic() - started) * 1000),
            "detail": detail,
            "application": identity,
        }

    try:
        parts = urlsplit(url)
        if (
            parts.scheme not in {"http", "https"}
            or not parts.hostname
            or parts.username is not None
            or parts.password is not None
            or parts.query
            or parts.fragment
        ):
            return finding(False, "invalid internal engine endpoint")
        if parts.port is not None and not 1 <= parts.port <= 65535:
            return finding(False, "invalid internal engine endpoint")
        body = bytearray()
        async with asyncio.timeout(timeout_s):
            async with httpx.AsyncClient(timeout=timeout_s, follow_redirects=False) as client:
                async with client.stream(
                    "GET",
                    url,
                    headers={
                        "User-Agent": "skeleton-app-runtime/1",
                        "Accept": "application/json",
                        "Accept-Encoding": "identity",
                    },
                ) as response:
                    status = response.status_code
                    if not 200 <= status < 300:
                        return finding(False, f"HTTP {status}")
                    advertised = response.headers.get("content-length")
                    if advertised is not None and (
                        not re.fullmatch(r"[0-9]{1,20}", advertised) or int(advertised) > 8192
                    ):
                        return finding(False, "invalid or oversized health response")
                    if response.headers.get("content-encoding", "identity").strip().lower() not in {
                        "",
                        "identity",
                    }:
                        return finding(False, "unsupported health response encoding")
                    async for chunk in response.aiter_bytes(chunk_size=4096):
                        if len(body) + len(chunk) > 8192:
                            return finding(False, "oversized health response")
                        body.extend(chunk)
        decoded = json.loads(
            body.decode("utf-8"),
            parse_float=finite_number,
            parse_constant=reject_constant,
            object_pairs_hook=unique_object,
        )
        candidate = decoded.get("application") if isinstance(decoded, dict) else None
        expected = {
            "name": manifest.name,
            "version": manifest.version,
            "component": "engine",
            "ingress_prefix": engine.ingress_prefix,
        }
        if not isinstance(candidate, dict) or any(
            candidate.get(key) != value for key, value in expected.items()
        ):
            return finding(False, "identity mismatch")
        if decoded.get("alive") is not True:
            return finding(False, "engine liveness not confirmed")
        # Project known identity fields only; never reflect arbitrary remote data.
        identity = expected
        return finding(True, "healthy")
    except (TimeoutError, httpx.TimeoutException):
        return finding(False, "timeout")
    except (httpx.HTTPError, httpx.InvalidURL, OSError):
        return finding(False, "engine transport unavailable")
    except (ValueError, RecursionError, OverflowError):
        return finding(False, "invalid health response")


@router.get(_MANIFEST.public_contract["bootstrap"])
def app_bootstrap() -> dict[str, object]:
    """Expose the sanitized canonical application contract to clients."""

    return public_bootstrap_payload()


async def _collect_runtime_status(timeout_ms: int) -> dict[str, object]:
    timeout_ms = max(250, min(int(timeout_ms), 10_000))
    bootstrap = public_bootstrap_payload()
    timeout_s = timeout_ms / 1000.0
    engine, mongo = await asyncio.gather(
        _probe_engine(timeout_s),
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
        # The single retained observation owns this worker even when all HTTP
        # readers detach. File-backed control-plane I/O must not block the API
        # event loop or multiply into new threads on every readiness request.
        report = await asyncio.to_thread(public_readiness)
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
        "ok": all(bool(item["ok"]) for item in services) and bool(product_readiness["available"]),
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "application": bootstrap["application"],
        "contract": bootstrap["contract"],
        "scope": "public-runtime",
        "services": services,
        "product": product_readiness,
    }


def _unobserved_status(detail: str) -> dict[str, object]:
    bootstrap = public_bootstrap_payload()
    return {
        "ok": False,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "application": bootstrap["application"],
        "contract": bootstrap["contract"],
        "scope": "public-runtime",
        "services": [
            {
                "name": name,
                "ok": name == "backend",
                "status": 200 if name == "backend" else None,
                "latency_ms": 0,
                "detail": "healthy" if name == "backend" else detail,
            }
            for name in ("backend", "skeleton", "mongo")
        ],
        "product": {
            "available": False,
            "canonical_actions": 0,
            "ready_actions": 0,
            "ready_pct": 0.0,
            "governed_unbound": 0,
            "unsafe_actions": 0,
            "policy_gaps": 0,
            "attestation_sha256": "",
            "detail": detail,
        },
    }


async def _runtime_status(timeout_ms: int, *, state=None) -> dict[str, object]:
    """Share one bounded observation per app; disconnected readers cannot cancel it."""
    timeout_ms = max(250, min(int(timeout_ms), 10_000))
    if state is None:
        return await _collect_runtime_status(timeout_ms)
    observation = getattr(state, "_public_runtime_observation", None)
    key = _engine_internal_base()
    if observation is not None:
        task = observation["task"]
        if (
            task.done()
            and observation["completed_at"] is not None
            and time.monotonic() - observation["completed_at"] <= 1.0
            and observation["key"] == key
        ):
            try:
                return task.result()
            except (Exception, asyncio.CancelledError):
                pass
        if not task.done() and observation["key"] != key:
            return _unobserved_status("observation pending for changed configuration")
    if observation is None or observation["task"].done():
        task = asyncio.create_task(_collect_runtime_status(timeout_ms))
        observation = {"task": task, "completed_at": None, "key": key}
        state._public_runtime_observation = observation

        def settled(done):
            observation["completed_at"] = time.monotonic()
            if not done.cancelled():
                done.exception()

        task.add_done_callback(settled)
    try:
        async with asyncio.timeout(timeout_ms / 1000.0):
            return await asyncio.shield(observation["task"])
    except TimeoutError:
        return _unobserved_status("observation pending beyond caller deadline")
    except Exception:
        return _unobserved_status("runtime observation unavailable")


@router.get(_MANIFEST.public_contract["status"])
async def app_status(request: Request, timeout_ms: int = 2500) -> dict[str, object]:
    """Aggregate the public application runtime behind one backend contract."""

    return await _runtime_status(timeout_ms, state=request.app.state)


@router.get(_MANIFEST.public_contract["ready"])
async def app_ready(request: Request, timeout_ms: int = 2500) -> JSONResponse:
    """Return a fail-closed readiness verdict for the assembled application."""

    payload = await _runtime_status(timeout_ms, state=request.app.state)
    return JSONResponse(status_code=200 if payload["ok"] else 503, content=payload)
