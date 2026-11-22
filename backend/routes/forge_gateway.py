"""Forge gateway: let signed-in app users reach sealed engine routes without the seal.

The Skeleton engine protects ``/api/v1/game/build`` and ``/api/v1/gameforge/*``
with an HMAC request seal (``x-gf-seal``). The seal secret must never reach a
browser or a mobile bundle. This backend-for-frontend (BFF) router:

* authenticates the caller with the existing application identity
  (``routes.gameforge_auth``; ``editor`` to start work, ``viewer`` to poll);
* forwards only an explicit allow-list of operations with validated bodies;
* mints a fresh, short-lived (30 s) PrincipalAuth seal per upstream request,
  ``forge-gateway.<actor>.<expiry>.<hmac>``, whose attester is a stable
  pseudonymous actor derived from the user, so the engine's own per-actor
  scoping isolates one user's builds from another's. (v2 nonce seals are not
  used: the engine's route-level ``require_seal`` verifies without a replay
  store and therefore refuses v2 by design. The seal only ever travels on the
  backend→engine hop, never to a client.)
* bounds request/response sizes, rate-limits build starts per user, never
  forwards client headers other than ``Idempotency-Key`` and ``X-Request-Id``,
  and maps engine failures to stable, non-leaky errors.

Configuration (all server-side):

``FORGE_GATEWAY_ENGINE_URL``   engine origin; falls back to ``SKELETON_INTERNAL_URL``.
``GF_SEAL_SECRET`` / ``GF_SEAL_KEYRING``   the engine seal key (shared with the engine).
``FORGE_GATEWAY_BUILDS_PER_MINUTE``   per-user build starts per minute (default 6).
``FORGE_GATEWAY_TIMEOUT_S``   upstream timeout for one request (default 30).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Deque, Dict, Literal, Mapping, Optional
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Path, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from routes.gameforge_auth import require_role

log = logging.getLogger("forge_gateway")

SCHEMA = "skeleton.forge_gateway.v1"
ATTESTER_PREFIX = "app-"
SEAL_PRINCIPAL = "forge-gateway"
SEAL_TTL_S = 30
MAX_BRIEF_CHARS = 4000
MAX_RESPONSE_BYTES = 16 * 1024 * 1024
_EXEC_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_IDEMPOTENCY = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")
_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_TENANT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_PASS_THROUGH_STATUSES = frozenset({400, 404, 409, 413, 422, 429})

router = APIRouter(prefix="/api/forge-gateway", tags=["forge-gateway"])

# Module-level dependency objects so deployments and tests can override them.
require_builder = require_role("editor")
require_reader = require_role("viewer")


# --------------------------------------------------------------------------- config
class GatewayConfigError(RuntimeError):
    """The gateway is not configured; surfaced as 503 without detail."""


@dataclass(frozen=True)
class GatewayConfig:
    engine_url: str
    builds_per_minute: int = 6
    timeout_s: float = 30.0

    @classmethod
    def from_env(cls) -> "GatewayConfig":
        raw = (os.getenv("FORGE_GATEWAY_ENGINE_URL") or os.getenv("SKELETON_INTERNAL_URL") or "").strip()
        if not raw:
            raise GatewayConfigError("engine url is not configured")
        try:
            per_minute = int(os.getenv("FORGE_GATEWAY_BUILDS_PER_MINUTE", "6"))
            timeout_s = float(os.getenv("FORGE_GATEWAY_TIMEOUT_S", "30"))
        except ValueError as exc:
            raise GatewayConfigError("gateway limits are invalid") from exc
        return cls(engine_url=normalise_engine_url(raw), builds_per_minute=per_minute, timeout_s=timeout_s)

    def __post_init__(self) -> None:
        if not 1 <= self.builds_per_minute <= 600:
            raise GatewayConfigError("FORGE_GATEWAY_BUILDS_PER_MINUTE must be 1..600")
        if not 1.0 <= self.timeout_s <= 300.0:
            raise GatewayConfigError("FORGE_GATEWAY_TIMEOUT_S must be 1..300")


def normalise_engine_url(raw: str) -> str:
    """Accept one plain http(s) origin; refuse userinfo, paths, queries and fragments."""
    parts = urlsplit(raw)
    if (
        parts.scheme not in {"http", "https"}
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
        or parts.path not in {"", "/"}
        or parts.query
        or parts.fragment
        or any(ord(ch) <= 32 or ord(ch) > 126 for ch in raw)
    ):
        raise GatewayConfigError("engine url must be a plain http(s) origin")
    return f"{parts.scheme}://{parts.netloc}"


# --------------------------------------------------------------------------- identity
@dataclass(frozen=True)
class Caller:
    actor: str
    tenant: str
    log_ref: str


def caller_from_user(user: Any) -> Caller:
    """Derive a stable, pseudonymous engine actor from the application user."""
    if not isinstance(user, Mapping):
        raise HTTPException(status_code=401, detail="Authentication required")
    owner = user.get("email") or user.get("user_id")
    if not isinstance(owner, str) or not owner.strip():
        raise HTTPException(status_code=401, detail="Authentication required")
    if user.get("dev_mode"):
        owner = "local-developer"  # auth not enforced (local development only)
    tenant_raw = user.get("tenant_id") or "default"
    tenant = tenant_raw.strip() if isinstance(tenant_raw, str) else ""
    if not _TENANT.fullmatch(tenant):
        raise HTTPException(status_code=403, detail="Tenant identity is unavailable")
    digest = hashlib.sha256(f"{tenant}\x00{owner.strip().lower()}".encode("utf-8")).hexdigest()
    return Caller(actor=f"{ATTESTER_PREFIX}{digest[:32]}", tenant=tenant, log_ref=digest[:10])


# --------------------------------------------------------------------------- rate limit
@dataclass
class SlidingWindowLimiter:
    limit: int
    window_s: float = 60.0
    clock: Callable[[], float] = time.monotonic
    _hits: Dict[str, Deque[float]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def check(self, key: str) -> Optional[float]:
        """Record a hit; return None when allowed, else seconds until a slot frees."""
        now = self.clock()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and now - hits[0] >= self.window_s:
                hits.popleft()
            if len(hits) >= self.limit:
                return max(0.0, self.window_s - (now - hits[0]))
            hits.append(now)
            if len(self._hits) > 50_000:  # bound memory under abuse
                for stale in [k for k, v in self._hits.items() if not v]:
                    self._hits.pop(stale, None)
            return None


# --------------------------------------------------------------------------- bodies
Playtest = Literal["off", "auto", "require"]


class GameBuildIn(BaseModel):
    """The subset of ``POST /api/v1/game/build`` an app user may set."""

    model_config = ConfigDict(extra="forbid")

    brief: str = Field(min_length=1, max_length=MAX_BRIEF_CHARS)
    playtest: Playtest = "auto"
    include_files: bool = False
    era: Optional[str] = Field(default=None, max_length=64)
    archetype: Optional[str] = Field(default=None, max_length=64)

    @field_validator("brief")
    @classmethod
    def _brief_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Describe the game you want to build.")
        return value.strip()


class GameforgeRunIn(BaseModel):
    """``POST /api/v1/gameforge/run``; server-side file writes are never allowed."""

    model_config = ConfigDict(extra="forbid")

    vision: str = Field(min_length=1, max_length=MAX_BRIEF_CHARS)
    era: Optional[str] = Field(default=None, max_length=64)
    archetype: Optional[str] = Field(default=None, max_length=64)
    playtest: Playtest = "off"
    repair_mode: Literal["apply", "suggest"] = "apply"
    include_files: bool = False
    answers: Optional[Dict[str, Any]] = None


class GameforgeIntakeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answers: Dict[str, Any] = Field(min_length=1)
    playtest: Playtest = "off"
    include_files: bool = False


# --------------------------------------------------------------------------- transport
Transport = Optional[httpx.AsyncBaseTransport]
_transport_override: Transport = None
_config_override: Optional[GatewayConfig] = None
_limiter: Optional[SlidingWindowLimiter] = None
_limiter_lock = threading.Lock()


def configure_for_tests(*, config: Optional[GatewayConfig], transport: Transport, clock: Callable[[], float] = time.monotonic) -> None:
    """Install an explicit config/transport (tests and embedded deployments)."""
    global _transport_override, _config_override, _limiter
    _config_override = config
    _transport_override = transport
    with _limiter_lock:
        _limiter = SlidingWindowLimiter(limit=config.builds_per_minute, clock=clock) if config else None


def _config() -> GatewayConfig:
    try:
        return _config_override or GatewayConfig.from_env()
    except GatewayConfigError as exc:
        log.error("forge_gateway.unconfigured reason=%s", exc)
        raise HTTPException(status_code=503, detail="Game building is not configured on this server.") from exc


def _build_limiter(config: GatewayConfig) -> SlidingWindowLimiter:
    global _limiter
    with _limiter_lock:
        if _limiter is None or _limiter.limit != config.builds_per_minute:
            _limiter = SlidingWindowLimiter(limit=config.builds_per_minute)
        return _limiter


def _mint(caller: Caller) -> str:
    from skeleton.api.hmac_seal import mint_seal

    seal = mint_seal(caller.actor, SEAL_TTL_S, principal=SEAL_PRINCIPAL)
    if not seal:
        log.error("forge_gateway.seal_unavailable")
        raise HTTPException(status_code=503, detail="Game building is not configured on this server.")
    return seal


def _forward_headers(caller: Caller, request_id: str, idempotency_key: Optional[str]) -> Dict[str, str]:
    headers = {
        "x-gf-seal": _mint(caller),
        "x-skeleton-tenant": caller.tenant,
        "x-request-id": request_id,
        "accept": "application/json",
    }
    if idempotency_key:
        headers["idempotency-key"] = idempotency_key
    return headers


def _request_id(raw: Optional[str]) -> str:
    return raw if raw and _REQUEST_ID.fullmatch(raw) else uuid.uuid4().hex


def _idempotency(raw: Optional[str]) -> Optional[str]:
    if raw is None or raw == "":
        return None
    if not _IDEMPOTENCY.fullmatch(raw):
        raise HTTPException(status_code=422, detail="Idempotency-Key must be 8-128 characters of [A-Za-z0-9._:-]")
    return raw


async def _call_engine(
    op: str,
    method: str,
    path: str,
    caller: Caller,
    *,
    body: Optional[Dict[str, Any]] = None,
    request_id: str,
    idempotency_key: Optional[str] = None,
) -> JSONResponse:
    config = _config()
    headers = _forward_headers(caller, request_id, idempotency_key)
    started = time.perf_counter()
    status = 0
    try:
        async with httpx.AsyncClient(
            base_url=config.engine_url,
            timeout=config.timeout_s,
            transport=_transport_override,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            async with client.stream(method, path, json=body, headers=headers) as upstream:
                status = upstream.status_code
                chunks = []
                size = 0
                async for chunk in upstream.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_RESPONSE_BYTES:
                        raise HTTPException(status_code=502, detail="The engine response was too large.")
                    chunks.append(chunk)
                raw = b"".join(chunks)
    except httpx.TimeoutException as exc:
        status = 504
        raise HTTPException(status_code=504, detail="The game engine did not answer in time.") from exc
    except httpx.HTTPError as exc:
        status = 502
        raise HTTPException(status_code=502, detail="The game engine is unavailable.") from exc
    finally:
        log.info(
            "forge_gateway.call op=%s actor=%s status=%s ms=%.0f rid=%s",
            op, caller.log_ref, status, (time.perf_counter() - started) * 1000, request_id,
        )
    try:
        payload = json.loads(raw) if raw else {}
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="The game engine returned an invalid response.") from exc
    if status < 400:
        if isinstance(payload, dict):
            payload.setdefault("gateway", {"schema": SCHEMA, "request_id": request_id})
        return JSONResponse(status_code=status, content=payload, headers={"x-request-id": request_id})
    if status in {401, 403} and not (isinstance(payload, dict) and isinstance(payload.get("detail"), dict) and payload["detail"].get("error") == "charter_denied"):
        log.error("forge_gateway.engine_rejected_credentials op=%s status=%s", op, status)
        raise HTTPException(status_code=502, detail="The game engine rejected this server's credentials.")
    if status in _PASS_THROUGH_STATUSES or status == 403:
        detail = payload.get("detail") if isinstance(payload, dict) else None
        if not isinstance(detail, (str, dict, list)):
            detail = "The game engine refused the request."
        headers = {"x-request-id": request_id}
        if status == 429 and "retry-after" in {k.lower() for k in upstream.headers.keys()}:
            headers["retry-after"] = upstream.headers["retry-after"]
        return JSONResponse(status_code=status, content={"detail": detail}, headers=headers)
    if status == 503:
        return JSONResponse(status_code=503, content={"detail": "The game engine is starting or busy. Try again shortly."},
                            headers={"x-request-id": request_id, "retry-after": "5"})
    raise HTTPException(status_code=502, detail="The game engine failed to process the request.")


# --------------------------------------------------------------------------- routes
@router.get("/status")
async def gateway_status(user: Any = Depends(require_reader)) -> Dict[str, Any]:
    """Whether builds can be started from the app (no secrets or URLs disclosed)."""
    from skeleton.api.hmac_seal import load_keyring

    caller_from_user(user)
    try:
        config = _config_override or GatewayConfig.from_env()
        configured = True
    except GatewayConfigError:
        config, configured = None, False
    return {
        "schema": SCHEMA,
        "engine_configured": configured,
        "seal_configured": bool(load_keyring()),
        "builds_per_minute": config.builds_per_minute if config else None,
        "operations": ["game.build.start", "game.build.status", "gameforge.run", "gameforge.intake"],
    }


@router.post("/game/build", status_code=202)
async def start_game_build(
    body: GameBuildIn,
    request: Request,
    user: Any = Depends(require_builder),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
) -> JSONResponse:
    caller = caller_from_user(user)
    key = _idempotency(idempotency_key)
    config = _config()
    retry = _build_limiter(config).check(caller.actor)
    if retry is not None:
        return JSONResponse(
            status_code=429,
            content={"detail": "Too many builds started. Try again in a minute."},
            headers={"retry-after": str(max(1, int(retry + 0.999)))},
        )
    response = await _call_engine(
        "game.build.start", "POST", "/api/v1/game/build", caller,
        body=body.model_dump(exclude_none=True), request_id=_request_id(request.headers.get("x-request-id")),
        idempotency_key=key,
    )
    if response.status_code == 202:
        payload = json.loads(response.body)
        execution_id = payload.get("execution_id")
        if isinstance(execution_id, str) and _EXEC_ID.fullmatch(execution_id):
            payload["status_ref"] = f"/api/forge-gateway/game/build/{execution_id}"
            rid = response.headers.get("x-request-id")
            return JSONResponse(status_code=202, content=payload, headers={"x-request-id": rid} if rid else None)
        raise HTTPException(status_code=502, detail="The game engine returned an invalid response.")
    return response


@router.get("/game/build/{execution_id}")
async def game_build_status(
    request: Request,
    execution_id: str = Path(min_length=1, max_length=128),
    user: Any = Depends(require_reader),
) -> JSONResponse:
    if not _EXEC_ID.fullmatch(execution_id):
        raise HTTPException(status_code=404, detail="build not found")
    caller = caller_from_user(user)
    return await _call_engine(
        "game.build.status", "GET", f"/api/v1/game/build/{execution_id}", caller,
        request_id=_request_id(request.headers.get("x-request-id")),
    )


@router.post("/gameforge/run")
async def gameforge_run(
    body: GameforgeRunIn,
    request: Request,
    user: Any = Depends(require_builder),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
) -> JSONResponse:
    caller = caller_from_user(user)
    retry = _build_limiter(_config()).check(caller.actor)
    if retry is not None:
        return JSONResponse(status_code=429, content={"detail": "Too many builds started. Try again in a minute."},
                            headers={"retry-after": str(max(1, int(retry + 0.999)))})
    return await _call_engine(
        "gameforge.run", "POST", "/api/v1/gameforge/run", caller,
        body=body.model_dump(exclude_none=True), request_id=_request_id(request.headers.get("x-request-id")),
        idempotency_key=_idempotency(idempotency_key),
    )


@router.post("/gameforge/intake")
async def gameforge_intake(
    body: GameforgeIntakeIn,
    request: Request,
    user: Any = Depends(require_builder),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
) -> JSONResponse:
    caller = caller_from_user(user)
    retry = _build_limiter(_config()).check(caller.actor)
    if retry is not None:
        return JSONResponse(status_code=429, content={"detail": "Too many builds started. Try again in a minute."},
                            headers={"retry-after": str(max(1, int(retry + 0.999)))})
    return await _call_engine(
        "gameforge.intake", "POST", "/api/v1/gameforge/intake", caller,
        body=body.model_dump(exclude_none=True), request_id=_request_id(request.headers.get("x-request-id")),
        idempotency_key=_idempotency(idempotency_key),
    )


__all__ = [
    "Caller",
    "GameBuildIn",
    "GatewayConfig",
    "GatewayConfigError",
    "SlidingWindowLimiter",
    "caller_from_user",
    "configure_for_tests",
    "normalise_engine_url",
    "require_builder",
    "require_reader",
    "router",
]
