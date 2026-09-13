"""Sealed HTTP surface for provider-neutral frontier execution."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field, StrictFloat, StrictInt, StrictStr

from skeleton.api.hmac_seal import require_seal
from skeleton.api.middleware import AuthError
from skeleton.frontier.agent_runtime import AgentRuntime
from skeleton.frontier.execution import ExecutionStatus, RuntimeBusy, RuntimeClosed
from skeleton.frontier.singleflight import IdempotencyConflict

router = APIRouter(prefix="/frontier", tags=["frontier"])


class ExecuteRequest(BaseModel):
    agent: StrictStr = Field(min_length=1, max_length=128)
    task: StrictStr = Field(min_length=1, max_length=20_000)
    context: dict[str, Any] = Field(default_factory=dict)
    request_id: StrictStr | None = Field(default=None, min_length=1, max_length=128)
    timeout: StrictFloat | StrictInt | None = Field(default=None, gt=0)

    class Config:
        extra = "forbid"


def _attester(x_gf_seal: str | None = Header(default=None, alias="x-gf-seal")) -> str:
    try:
        return require_seal(x_gf_seal)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail="invalid seal") from exc


def _runtime(request: Request) -> AgentRuntime:
    runtime = getattr(request.app.state, "frontier_runtime", None)
    if runtime is None:
        raise HTTPException(status_code=503, detail="frontier runtime unavailable")
    return runtime


@router.get("/agents")
async def agents(runtime: AgentRuntime = Depends(_runtime), attester: str = Depends(_attester)):
    return {
        "agents": [
            {"name": name, "capabilities": sorted(agent.capabilities)}
            for name, agent in sorted(runtime.agents.items())
        ]
    }


@router.get("/status")
async def status(runtime: AgentRuntime = Depends(_runtime), attester: str = Depends(_attester)):
    return runtime.stats()


@router.post("/execute")
async def execute(
    body: ExecuteRequest,
    response: Response,
    runtime: AgentRuntime = Depends(_runtime),
    attester: str = Depends(_attester),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    key = None
    if idempotency_key is not None:
        if not idempotency_key.strip() or len(idempotency_key) > 128:
            raise HTTPException(status_code=422, detail="invalid idempotency key")
        key = hashlib.sha256(json.dumps([attester, body.agent, idempotency_key]).encode()).hexdigest()
    try:
        result = await runtime.execute(
            body.agent,
            body.task,
            context=body.context,
            request_id=body.request_id,
            timeout=body.timeout,
            idempotency_key=key,
        )
    except IdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail="idempotency key conflicts with prior request") from exc
    except RuntimeBusy as exc:
        raise HTTPException(
            status_code=429, detail="runtime capacity unavailable", headers={"Retry-After": "1"}
        ) from exc
    except RuntimeClosed as exc:
        raise HTTPException(status_code=503, detail="runtime is closed") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="agent capability is not authorized") from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="unknown agent") from exc
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail="invalid execution request") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="runtime unavailable") from exc
    response.headers["X-Request-Id"] = result.request_id
    if result.status is ExecutionStatus.TIMED_OUT:
        response.status_code = 504
    elif not result.succeeded:
        response.status_code = 502
    return result.as_dict()
