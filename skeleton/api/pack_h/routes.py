"""Pack H HTTP surface.

* ``GET /admit/pressure`` and ``GET /admit/pressure/{tenant_id}``: the
  read-only pressure contract the gate plane consumes. 503 when ``shed``
  (with ``Retry-After``), 200 otherwise, so a probe can use status alone.
* ``/pack-h/records``: tenant-scoped records API. Writes require
  ``Idempotency-Key`` and emit ``record.*`` outbox events transactionally.
* ``GET /pack-h/outbox/stats``: relay backlog counts for ops.

The router is exported but not mounted here; mount with
``app.include_router(pack_h_router, prefix="/api/v1")``.
"""

from __future__ import annotations

import math
import os
import re
import threading
from dataclasses import dataclass
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Header, Query, Request
from starlette.responses import JSONResponse, Response

from skeleton.api.pack_h import admit_pressure
from skeleton.api.pack_h.idempotency import HEADER, run_idempotent
from skeleton.persistence.pack_h.idempotency_store import IdempotencyStore
from skeleton.persistence.pack_h.records import RecordConflict, RecordError, RecordNotFound, RecordStore

_TENANT_RE = re.compile(r"^[A-Za-z0-9._:\-]{1,128}$")

router = APIRouter(tags=["pack-h"])


@dataclass
class PackHServices:
    records: RecordStore
    idempotency: IdempotencyStore


_services: Optional[PackHServices] = None
_services_lock = threading.Lock()


def _default_services() -> PackHServices:
    # Assumption: no settings block exists yet for Pack H stores; use env
    # paths and fall back to in-memory (process-local) SQLite.
    records_path = os.environ.get("SKELETON_PACK_H_RECORDS_DB", ":memory:")
    idem_path = os.environ.get("SKELETON_PACK_H_IDEMPOTENCY_DB", ":memory:")
    return PackHServices(records=RecordStore(records_path), idempotency=IdempotencyStore(idem_path))


def services() -> PackHServices:
    global _services
    with _services_lock:
        if _services is None:
            _services = _default_services()
        return _services


def install_services(svc: Optional[PackHServices]) -> None:
    global _services
    with _services_lock:
        _services = svc


def _error(status: int, error: str, **extra: Any) -> JSONResponse:
    return JSONResponse({"error": error, **extra}, status_code=status)


def _pressure_response(snap: admit_pressure.PressureSnapshot) -> JSONResponse:
    headers: Dict[str, str] = {"Cache-Control": "no-store"}
    retry = snap.retry_after_header()
    if retry is not None:
        headers["Retry-After"] = retry
    status = 503 if snap.state is admit_pressure.PressureState.SHED else 200
    return JSONResponse(snap.as_dict(), status_code=status, headers=headers)


@router.get("/admit/pressure")
def get_pressure() -> JSONResponse:
    return _pressure_response(admit_pressure.snapshot())


@router.get("/admit/pressure/{tenant_id}")
def get_tenant_pressure(tenant_id: str) -> Response:
    if not _TENANT_RE.fullmatch(tenant_id):
        return _error(400, "invalid_tenant_id")
    return _pressure_response(admit_pressure.snapshot(tenant_id))


def _tenant(x_tenant_id: Optional[str]) -> Optional[str]:
    if x_tenant_id is None or not _TENANT_RE.fullmatch(x_tenant_id):
        return None
    return x_tenant_id


def _shed_guard(tenant: str) -> Optional[Response]:
    snap = admit_pressure.snapshot(tenant)
    if snap.state is admit_pressure.PressureState.SHED:
        retry = snap.retry_after_header() or str(max(1, math.ceil(snap.retry_after_s or 1)))
        return JSONResponse(
            {"error": "shed", "retry_after_s": snap.retry_after_s}, status_code=503, headers={"Retry-After": retry}
        )
    return None


@router.post("/pack-h/records")
def create_record(
    request: Request,
    payload: Dict[str, Any] = Body(...),
    x_tenant_id: Optional[str] = Header(default=None),
    idempotency_key: Optional[str] = Header(default=None, alias=HEADER),
) -> Response:
    tenant = _tenant(x_tenant_id)
    if tenant is None:
        return _error(400, "tenant_required")
    shed = _shed_guard(tenant)
    if shed is not None:
        return shed
    svc = services()

    def handler():
        kind = payload.get("kind")
        body = payload.get("body", {})
        rid = payload.get("record_id")
        try:
            rec = svc.records.create(tenant, kind, body, record_id=rid)
        except RecordConflict as exc:
            return 409, {"error": "record_exists", "current_version": exc.current_version}
        except RecordError as exc:
            return 422, {"error": "invalid_record", "detail": str(exc)}
        return 201, rec.as_dict()

    return run_idempotent(svc.idempotency, scope=f"{tenant}:records.create", key=idempotency_key,
                          method="POST", path=request.url.path, body=payload, handler=handler)


@router.get("/pack-h/records")
def list_records(
    x_tenant_id: Optional[str] = Header(default=None),
    kind: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> Response:
    tenant = _tenant(x_tenant_id)
    if tenant is None:
        return _error(400, "tenant_required")
    recs = services().records.list(tenant, kind=kind, limit=limit)
    return JSONResponse({"items": [r.as_dict() for r in recs]})


@router.get("/pack-h/records/{record_id}")
def get_record(record_id: str, x_tenant_id: Optional[str] = Header(default=None)) -> Response:
    tenant = _tenant(x_tenant_id)
    if tenant is None:
        return _error(400, "tenant_required")
    try:
        rec = services().records.get(tenant, record_id)
    except RecordNotFound:
        return _error(404, "record_not_found")
    return JSONResponse(rec.as_dict(), headers={"ETag": f'"{rec.version}"'})


def _parse_if_match(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    v = value.strip().strip('"')
    if not v.isdigit():
        raise ValueError("If-Match must be a record version")
    return int(v)


@router.put("/pack-h/records/{record_id}")
def update_record(
    record_id: str,
    request: Request,
    payload: Dict[str, Any] = Body(...),
    x_tenant_id: Optional[str] = Header(default=None),
    if_match: Optional[str] = Header(default=None),
    idempotency_key: Optional[str] = Header(default=None, alias=HEADER),
) -> Response:
    tenant = _tenant(x_tenant_id)
    if tenant is None:
        return _error(400, "tenant_required")
    try:
        expected = _parse_if_match(if_match)
    except ValueError as exc:
        return _error(400, "invalid_if_match", detail=str(exc))
    shed = _shed_guard(tenant)
    if shed is not None:
        return shed
    svc = services()

    def handler():
        try:
            rec = svc.records.update(tenant, record_id, payload.get("body", {}), expected_version=expected)
        except RecordNotFound:
            return 404, {"error": "record_not_found"}
        except RecordConflict as exc:
            return 412, {"error": "version_mismatch", "current_version": exc.current_version}
        except RecordError as exc:
            return 422, {"error": "invalid_record", "detail": str(exc)}
        return 200, rec.as_dict()

    return run_idempotent(svc.idempotency, scope=f"{tenant}:records.update", key=idempotency_key,
                          method="PUT", path=request.url.path, body={"payload": payload, "if_match": expected},
                          handler=handler)


@router.delete("/pack-h/records/{record_id}")
def delete_record(
    record_id: str,
    request: Request,
    x_tenant_id: Optional[str] = Header(default=None),
    if_match: Optional[str] = Header(default=None),
    idempotency_key: Optional[str] = Header(default=None, alias=HEADER),
) -> Response:
    tenant = _tenant(x_tenant_id)
    if tenant is None:
        return _error(400, "tenant_required")
    try:
        expected = _parse_if_match(if_match)
    except ValueError as exc:
        return _error(400, "invalid_if_match", detail=str(exc))
    svc = services()

    def handler():
        try:
            rec = svc.records.delete(tenant, record_id, expected_version=expected)
        except RecordNotFound:
            return 404, {"error": "record_not_found"}
        except RecordConflict as exc:
            return 412, {"error": "version_mismatch", "current_version": exc.current_version}
        return 200, {"deleted": True, "version": rec.version}

    return run_idempotent(svc.idempotency, scope=f"{tenant}:records.delete", key=idempotency_key,
                          method="DELETE", path=request.url.path, body={"if_match": expected}, handler=handler)


@router.get("/pack-h/outbox/stats")
def outbox_stats() -> JSONResponse:
    return JSONResponse(services().records.outbox.counts())
