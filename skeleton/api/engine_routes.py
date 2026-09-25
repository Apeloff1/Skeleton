"""Sealed engine execution endpoints backed by durable cognitive state."""

from __future__ import annotations

from datetime import datetime
import hmac
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from skeleton.api.engine_authority import EngineAuthorityError
from skeleton.api.engine_service import (
    EngineExecutionCommand,
    EngineExecutionService,
    EngineServiceError,
    EngineSubmissionConflict,
)
from skeleton.persistence.execution_repository import (
    ExecutionRepositoryConflict,
    ExecutionRepositoryError,
)


router = APIRouter(prefix="/engine", tags=["engine"])


class EngineSubmitBody(BaseModel):
    actor_id: str = Field(min_length=1, max_length=512)
    tenant_id: str = Field(min_length=1, max_length=512)
    command: dict[str, Any]


class EngineCancelBody(BaseModel):
    actor_id: str = Field(min_length=1, max_length=512)
    tenant_id: str = Field(min_length=1, max_length=512)
    reason: str = Field(min_length=1, max_length=2048)


class EngineToolApprovalBody(BaseModel):
    actor_id: str = Field(min_length=1, max_length=512)
    tenant_id: str = Field(min_length=1, max_length=512)
    call_id: str = Field(min_length=1, max_length=256)
    tool_id: str = Field(min_length=1, max_length=128)
    arguments_digest: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    idempotency_key: str = Field(min_length=1, max_length=1024)
    expires_at: datetime


def _engine_service() -> EngineExecutionService:
    from skeleton.api.server import get_state

    service = getattr(get_state(), "engine_execution_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="engine execution service unavailable",
        )
    return service


def _engine_coordinator():
    from skeleton.api.server import get_state

    return getattr(get_state(), "engine_execution_coordinator", None)


def _engine_service_token() -> str:
    from skeleton.config.settings import get_settings

    token = get_settings().engine.service_token.get_secret_value()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="engine service authentication is not configured",
        )
    return token


def _verified_service_principal(
    request: Request,
    expected_token: str,
) -> str:
    authorization = request.headers.get("authorization", "")
    scheme, separator, presented = authorization.partition(" ")
    if (
        not separator
        or scheme.lower() != "bearer"
        or not presented
        or not hmac.compare_digest(presented, expected_token)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="engine service authentication failed",
        )
    principal = request.headers.get("x-zaibatsu-attester")
    if not principal:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="verified service principal required",
        )
    return principal


def _raise_engine_error(exc: Exception) -> None:
    if isinstance(exc, EngineAuthorityError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    if isinstance(exc, EngineSubmissionConflict):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    if isinstance(exc, ExecutionRepositoryConflict):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    if isinstance(exc, (EngineServiceError, ExecutionRepositoryError)):
        detail = str(exc)
        code = (
            status.HTTP_404_NOT_FOUND
            if "unknown" in detail.lower()
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        raise HTTPException(status_code=code, detail=detail) from exc
    if isinstance(exc, (ValueError, TypeError)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    raise exc


@router.post("/executions", status_code=status.HTTP_202_ACCEPTED)
async def submit_execution(
    body: EngineSubmitBody,
    request: Request,
    service: EngineExecutionService = Depends(_engine_service),
    service_token: str = Depends(_engine_service_token),
    coordinator=Depends(_engine_coordinator),
) -> dict[str, Any]:
    principal = _verified_service_principal(request, service_token)
    try:
        command = EngineExecutionCommand.from_dict(body.command)
        ack = service.submit(
            command,
            verified_service_principal=principal,
            actor_id=body.actor_id,
            tenant_id=body.tenant_id,
        )
        if coordinator is not None:
            await coordinator.ensure_started(command)
    except Exception as exc:
        _raise_engine_error(exc)
        raise
    return ack.as_dict()


@router.get("/executions/{execution_id}")
def execution_status(
    execution_id: str,
    request: Request,
    actor_id: str = Query(..., min_length=1, max_length=512),
    tenant_id: str = Query(..., min_length=1, max_length=512),
    service: EngineExecutionService = Depends(_engine_service),
    service_token: str = Depends(_engine_service_token),
) -> dict[str, Any]:
    principal = _verified_service_principal(request, service_token)
    try:
        return service.status(
            execution_id,
            verified_service_principal=principal,
            actor_id=actor_id,
            tenant_id=tenant_id,
        ).as_dict()
    except Exception as exc:
        _raise_engine_error(exc)
        raise


@router.post("/executions/{execution_id}/cancel")
def cancel_execution(
    execution_id: str,
    body: EngineCancelBody,
    request: Request,
    service: EngineExecutionService = Depends(_engine_service),
    service_token: str = Depends(_engine_service_token),
) -> dict[str, Any]:
    principal = _verified_service_principal(request, service_token)
    try:
        return service.cancel(
            execution_id,
            verified_service_principal=principal,
            actor_id=body.actor_id,
            tenant_id=body.tenant_id,
        ).as_dict()
    except Exception as exc:
        _raise_engine_error(exc)
        raise


@router.get("/executions/{execution_id}/tool-approvals/pending")
def pending_tool_approvals(
    execution_id: str,
    request: Request,
    actor_id: str = Query(..., min_length=1, max_length=512),
    tenant_id: str = Query(..., min_length=1, max_length=512),
    service: EngineExecutionService = Depends(_engine_service),
    service_token: str = Depends(_engine_service_token),
) -> dict[str, Any]:
    principal = _verified_service_principal(request, service_token)
    try:
        pending = service.pending_tool_approvals(
            execution_id,
            verified_service_principal=principal,
            actor_id=actor_id,
            tenant_id=tenant_id,
        )
    except Exception as exc:
        _raise_engine_error(exc)
        raise
    return {
        "execution_id": execution_id,
        "pending": [dict(item) for item in pending],
    }


@router.post(
    "/executions/{execution_id}/tool-approvals",
    status_code=status.HTTP_202_ACCEPTED,
)
async def approve_tool_call(
    execution_id: str,
    body: EngineToolApprovalBody,
    request: Request,
    service: EngineExecutionService = Depends(_engine_service),
    service_token: str = Depends(_engine_service_token),
    coordinator=Depends(_engine_coordinator),
) -> dict[str, Any]:
    principal = _verified_service_principal(request, service_token)
    try:
        approval = service.approve_tool_call(
            execution_id,
            verified_service_principal=principal,
            actor_id=body.actor_id,
            tenant_id=body.tenant_id,
            call_id=body.call_id,
            tool_id=body.tool_id,
            arguments_digest=body.arguments_digest,
            idempotency_key=body.idempotency_key,
            expires_at=body.expires_at,
        )
        if coordinator is not None:
            await coordinator.ensure_execution(execution_id)
    except Exception as exc:
        _raise_engine_error(exc)
        raise
    return approval.as_dict()


@router.get("/executions/{execution_id}/events")
def execution_events(
    execution_id: str,
    request: Request,
    actor_id: str = Query(..., min_length=1, max_length=512),
    tenant_id: str = Query(..., min_length=1, max_length=512),
    service: EngineExecutionService = Depends(_engine_service),
    service_token: str = Depends(_engine_service_token),
) -> dict[str, Any]:
    principal = _verified_service_principal(request, service_token)
    try:
        return service.events(
            execution_id,
            verified_service_principal=principal,
            actor_id=actor_id,
            tenant_id=tenant_id,
        )
    except Exception as exc:
        _raise_engine_error(exc)
        raise


__all__ = [
    "router",
    "_engine_coordinator",
    "_engine_service",
    "_engine_service_token",
]
