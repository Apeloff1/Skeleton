"""Sealed engine execution endpoints backed by durable cognitive state."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
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
    command: dict[str, Any]


class EngineCancelBody(BaseModel):
    reason: str = Field(min_length=1, max_length=2048)


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


def _verified_service_principal(request: Request) -> str:
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
    coordinator=Depends(_engine_coordinator),
) -> dict[str, Any]:
    principal = _verified_service_principal(request)
    try:
        command = EngineExecutionCommand.from_dict(body.command)
        ack = service.submit(
            command,
            verified_service_principal=principal,
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
    service: EngineExecutionService = Depends(_engine_service),
) -> dict[str, Any]:
    principal = _verified_service_principal(request)
    try:
        return service.status(
            execution_id,
            verified_service_principal=principal,
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
) -> dict[str, Any]:
    del body
    principal = _verified_service_principal(request)
    try:
        return service.cancel(
            execution_id,
            verified_service_principal=principal,
        ).as_dict()
    except Exception as exc:
        _raise_engine_error(exc)
        raise


@router.get("/executions/{execution_id}/events")
def execution_events(
    execution_id: str,
    request: Request,
    service: EngineExecutionService = Depends(_engine_service),
) -> dict[str, Any]:
    principal = _verified_service_principal(request)
    try:
        return service.events(
            execution_id,
            verified_service_principal=principal,
        )
    except Exception as exc:
        _raise_engine_error(exc)
        raise


__all__ = ["router", "_engine_coordinator", "_engine_service"]
