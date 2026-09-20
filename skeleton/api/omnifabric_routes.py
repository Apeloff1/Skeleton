"""OmniFabric HTTP routes — standalone FastAPI router (extend-only).

Exposes proof-as-route surfaces matching gameforge-rs fabric doctrine
(``/api/fabric/verify-chain`` spirit). This module does **not** modify
``skeleton.api.server`` lifespan or include itself automatically — callers
``include_router`` explicitly, keeping security/lifespan PRs undisturbed.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException

from skeleton.kernel.omnifabric.adapters import wire_append_request
from skeleton.kernel.omnifabric.doctrine import ROUTE_PREFIX, SIBLING_MODULE, SIBLING_REPO
from skeleton.kernel.omnifabric.errors import (
    ChainBroken,
    OmniFabricError,
    OutboxFull,
    QueryBoundsError,
    ReplayConflict,
)
from skeleton.kernel.omnifabric.service import OmniFabricService

router = APIRouter(prefix=ROUTE_PREFIX, tags=["omnifabric"])

_service: Optional[OmniFabricService] = None


def get_omnifabric_service() -> OmniFabricService:
    global _service
    if _service is None:
        _service = OmniFabricService()
    return _service


def set_omnifabric_service(service: OmniFabricService | None) -> None:
    global _service
    _service = service


@router.get("/meta")
def omnifabric_meta() -> Dict[str, Any]:
    return {
        "surface": "OmniFabric",
        "sibling": SIBLING_REPO,
        "module": SIBLING_MODULE,
        "prefix": ROUTE_PREFIX,
        "note": "Standalone router — not auto-mounted on api.server lifespan",
    }


@router.post("/append")
def omnifabric_append(body: Dict[str, Any]) -> Dict[str, Any]:
    svc = get_omnifabric_service()
    kwargs = wire_append_request(body)
    if not kwargs["ledger"] or not kwargs["kind"]:
        raise HTTPException(status_code=400, detail="ledger and kind are required")
    try:
        ev = svc.append(**kwargs)
    except OutboxFull as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except OmniFabricError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"event": ev}


@router.get("/tail")
def omnifabric_tail(ledger: str, limit: int = 128) -> Dict[str, Any]:
    svc = get_omnifabric_service()
    try:
        events = svc.tail(ledger, limit)
    except (ValueError, QueryBoundsError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ledger": ledger, "events": events}


@router.get("/verify-chain")
def omnifabric_verify_chain(full: bool = False) -> Dict[str, Any]:
    """Proof as a route, not a promise (RS doctrine)."""
    return get_omnifabric_service().verify(full_evidence=full)


@router.get("/status")
def omnifabric_status() -> Dict[str, Any]:
    return get_omnifabric_service().status()


@router.post("/query")
def omnifabric_query(body: Dict[str, Any]) -> Dict[str, Any]:
    svc = get_omnifabric_service()
    try:
        return svc.query(
            ledger=body.get("ledger"),
            kind=body.get("kind"),
            min_seq=body.get("min_seq"),
            max_seq=body.get("max_seq"),
            attester=body.get("attester"),
            since_ts=body.get("since_ts"),
            until_ts=body.get("until_ts"),
            limit=int(body.get("limit") or 128),
            newest_first=bool(body.get("newest_first", True)),
        )
    except QueryBoundsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/reconcile")
def omnifabric_reconcile() -> Dict[str, Any]:
    return get_omnifabric_service().reconcile()


@router.post("/checkpoint")
def omnifabric_checkpoint() -> Dict[str, Any]:
    return {"checkpoint": get_omnifabric_service().checkpoint_tail()}


@router.post("/ledgers/register")
def omnifabric_register_ledger(body: Dict[str, Any]) -> Dict[str, Any]:
    name = str(body.get("name") or "")
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    return get_omnifabric_service().register_ledger(
        name, str(body.get("description") or ""), **dict(body.get("metadata") or {})
    )


@router.get("/ledgers")
def omnifabric_list_ledgers() -> Dict[str, Any]:
    svc = get_omnifabric_service()
    return {"ledgers": [i.to_dict() for i in svc.catalog.list_ledgers()]}
