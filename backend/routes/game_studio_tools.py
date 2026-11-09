"""Authenticated studio command discovery and exact owner-scoped execution."""

import hashlib
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import Field, model_validator

from core.game_studio_tools import execute_studio_command
from routes.game_learning import Request, _call, _scope
from routes.gameforge_auth import get_current_user
from skeleton.jeeves.game_studio_tools import MAX_RESULT, StudioCommand, studio_command_catalog

router = APIRouter(prefix="/game-studio-tools", tags=["Jeeves studio commands"])


class StudioToolRequest(Request):
    operation: str = Field(min_length=1, max_length=64)
    project_id: str = Field(min_length=1, max_length=128)
    payload: dict[str, Any] = Field(default_factory=dict, max_length=64)

    @model_validator(mode="after")
    def typed_command(self):
        StudioCommand(self.operation, self.project_id, self.payload)
        return self


@router.get("/catalog")
async def catalog(user=Depends(get_current_user)):
    _scope(user)
    return studio_command_catalog()


@router.post("/execute")
async def execute(body: StudioToolRequest, user=Depends(get_current_user)):
    command = StudioCommand(body.operation, body.project_id, body.payload)
    if (command.operation == "game.studio.curriculum.automation.commit"
            and user.get("role") not in {"editor", "admin"}):
        raise HTTPException(403, detail={
            "code": "jeeves_training_write_denied",
            "message": "A project editor must authorize this exact source change.",
        })
    result = jsonable_encoder(await _call(execute_studio_command(_scope(user), command)))
    raw = json.dumps(
        result, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()
    if len(raw) > MAX_RESULT:
        from core.game_learning import GameLearningError

        async def too_large():
            raise GameLearningError(
                "studio_result_large", "Inspect a smaller studio section or evidence page.", 422
            )

        return await _call(too_large())
    return {
        "schema_version": "skeleton.game.studio_tool_receipt.v1",
        "command_digest": command.digest,
        "operation": command.operation,
        "project_id": command.project_id,
        "result_digest": hashlib.sha256(raw).hexdigest(),
        "result": result,
    }
