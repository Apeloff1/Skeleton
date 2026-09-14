"""External witness seam for deployment checkpoint publication trust.

Witnesses may read the current canonical signing target and submit already-signed
Ed25519 receipts. The server never accepts witness private keys and never signs on a
witness's behalf. Operator-only endpoints expose quorum status and portable trust
advancement/continuity proofs from the same runtime used by deployment assurance.
"""
from __future__ import annotations

from dataclasses import asdict
import hmac
import os

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from core.deployment_checkpoint_pin_ledger import (
    DeploymentCheckpointPinLedgerError,
    DeploymentCheckpointPinRejected,
)
from core.deployment_checkpoint_pin_wire import decode_deployment_checkpoint_pin_receipt
from routes.ops import _control_plane, _require_ops

router = APIRouter(
    prefix="/api/admin/deployment-checkpoint-trust",
    tags=["deployment-checkpoint-trust"],
)


class WitnessReceiptInput(BaseModel):
    receipt: dict = Field(default_factory=dict)


def _witness_token_required(provided: str) -> None:
    expected = os.environ.get("DEPLOYMENT_CHECKPOINT_WITNESS_TOKEN", "")
    if not expected:
        raise HTTPException(status_code=503, detail="deployment checkpoint witness API is disabled")
    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=403, detail="unauthorized deployment checkpoint witness")


def _runtime():
    """Return the deployment-authoritative witness runtime.

    There must be exactly one pin ledger/runtime per ProductControlPlane. Creating a
    route-local runtime would split submitted evidence from the state consumed by
    assurance and deployment preflight.
    """
    return _control_plane().deployment_checkpoint_pins


@router.get("/target")
async def current_checkpoint_witness_target(
    witness_token: str = Header("", alias="X-Deployment-Witness-Token"),
):
    _witness_token_required(witness_token)
    target = _runtime().current_target()
    if target is None:
        raise HTTPException(status_code=404, detail="no deployment checkpoint publication exists")
    return asdict(target)


@router.post("/receipts")
async def ingest_checkpoint_witness_receipt(
    body: WitnessReceiptInput,
    witness_token: str = Header("", alias="X-Deployment-Witness-Token"),
):
    _witness_token_required(witness_token)
    try:
        runtime = _runtime()
        receipt = decode_deployment_checkpoint_pin_receipt(body.receipt)
        event = runtime.observe(receipt)
        quorum = runtime.quorum(publication_sequence=receipt.publication.sequence)
        return {
            "accepted": True,
            "event": asdict(event),
            "quorum": None if quorum is None else asdict(quorum),
            "requirement_satisfied": runtime.requirement_satisfied(),
        }
    except DeploymentCheckpointPinRejected as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (DeploymentCheckpointPinLedgerError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/status")
async def checkpoint_witness_status(token: str = Query("")):
    _require_ops(token)
    try:
        return _runtime().status()
    except (DeploymentCheckpointPinLedgerError, ValueError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/bundle")
async def checkpoint_witness_bundle(
    publication_sequence: int | None = Query(default=None, ge=1),
    token: str = Query(""),
):
    _require_ops(token)
    try:
        bundle = _runtime().portable_bundle(publication_sequence=publication_sequence)
        return asdict(bundle)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="deployment checkpoint publication not found") from exc
    except DeploymentCheckpointPinRejected as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (DeploymentCheckpointPinLedgerError, ValueError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/trust-advance")
async def checkpoint_witness_trust_advance(
    publication_sequence: int | None = Query(default=None, ge=1),
    token: str = Query(""),
):
    """Export a portable append-only bridge from a fresh witnessed anchor to current head."""
    _require_ops(token)
    try:
        runtime = _runtime()
        packet = (
            runtime.advance_latest_witnessed()
            if publication_sequence is None
            else runtime.trust_advance(publication_sequence=publication_sequence)
        )
        return asdict(packet)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="deployment checkpoint publication not found") from exc
    except DeploymentCheckpointPinRejected as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (DeploymentCheckpointPinLedgerError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/continuity")
async def checkpoint_witness_continuity(
    previous_publication_sequence: int | None = Query(default=None, ge=1),
    token: str = Query(""),
):
    """Export a portable proof with fresh independent witness quorums at both endpoints."""
    _require_ops(token)
    try:
        runtime = _runtime()
        packet = (
            runtime.latest_witnessed_continuity()
            if previous_publication_sequence is None
            else runtime.witnessed_continuity(
                previous_publication_sequence=previous_publication_sequence,
            )
        )
        return asdict(packet)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="deployment checkpoint publication not found") from exc
    except DeploymentCheckpointPinRejected as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (DeploymentCheckpointPinLedgerError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
