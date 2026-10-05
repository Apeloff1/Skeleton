
from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel

from gameforge.enterprise.auth import Principal, get_principal
from gameforge.enterprise.zaibatsu_security import SECURITY

router = APIRouter(prefix="/security", tags=["zaibatsu-security"])


class FreezeBody(BaseModel):
    reason: str = "manual"


class UnfreezeBody(BaseModel):
    emperor_seal: bool = False
    actor: str = "user"


class UnblockBody(BaseModel):
    user_id: str
    emperor_seal: bool = False


class InspectBody(BaseModel):
    text: str
    path: str = ""


@router.get("/status")
async def security_status(principal: Principal = Depends(get_principal)):
    return SECURITY.status()


@router.post("/freeze")
async def security_freeze(req: FreezeBody, principal: Principal = Depends(get_principal)):
    return SECURITY.freeze(req.reason)


@router.post("/unfreeze")
async def security_unfreeze(req: UnfreezeBody, principal: Principal = Depends(get_principal)):
    return SECURITY.unfreeze(emperor_seal=req.emperor_seal, actor=req.actor or principal.user_id)


@router.post("/unblock")
async def security_unblock(req: UnblockBody, principal: Principal = Depends(get_principal)):
    return SECURITY.unblock_user(req.user_id, emperor_seal=req.emperor_seal)


@router.post("/inspect")
async def security_inspect(req: InspectBody, principal: Principal = Depends(get_principal)):
    return SECURITY.inspect_text(req.text, user_id=principal.user_id, path=req.path)


@router.get("/integrity")
async def security_integrity(principal: Principal = Depends(get_principal)):
    return SECURITY.verify_integrity_tail(8)


@router.get("/appwide")
async def security_appwide(principal: Principal = Depends(get_principal)):
    from gameforge.enterprise.zaibatsu_appwide import appwide_status, install_appwide_zaibatsu
    install_appwide_zaibatsu()
    return appwide_status()
