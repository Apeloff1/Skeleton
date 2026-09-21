"""Public application assembly/bootstrap and aggregate runtime status."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import os
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import APIRouter

from skeleton.app.assembly import load_manifest
from skeleton.app.bootstrap import public_bootstrap_payload
from core.databases import core_db

router = APIRouter(prefix="/api/app", tags=["application"])


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
            response.read(256)
        ok = 200 <= status < 400
        return {
            "name": "skeleton",
            "ok": ok,
            "status": status,
            "latency_ms": int((time.monotonic() - started) * 1000),
            "detail": "healthy" if ok else f"unexpected HTTP status {status}",
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


@router.get("/bootstrap")
def app_bootstrap() -> dict[str, object]:
    """Expose the sanitized canonical application contract to clients."""

    return public_bootstrap_payload()


@router.get("/status")
async def app_status(timeout_ms: int = 2500) -> dict[str, object]:
    """Aggregate the public application runtime behind one backend contract."""

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
    return {
        "ok": all(bool(item["ok"]) for item in services),
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "application": bootstrap["application"],
        "scope": "public-runtime",
        "services": services,
    }
