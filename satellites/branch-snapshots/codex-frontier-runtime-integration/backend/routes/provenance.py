"""routes/provenance.py — CRYPTOGRAPHIC PROVENANCE API (Segments 4-5).

Append-only, tamper-evident event chain per build + a verification pass.
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from core import provenance_ledger as pl

router = APIRouter(prefix="/api/provenance", tags=["provenance"])


class AppendReq(BaseModel):
    kind: str
    data: dict | None = None
    agent: str = "user"
    model: str | None = None


@router.post("/{build_id}/append")
def append(build_id: str, req: AppendReq):
    return pl.append(build_id, req.kind, req.data, agent=req.agent, model=req.model)


@router.get("/{build_id}/chain")
def chain(build_id: str, limit: int = 200):
    return pl.chain(build_id, limit=limit)


@router.get("/{build_id}/verify")
def verify(build_id: str):
    return pl.verify(build_id)


@router.get("/{build_id}/artifact/{gid}")
def artifact(build_id: str, gid: str):
    return pl.artifact_provenance(build_id, gid)
