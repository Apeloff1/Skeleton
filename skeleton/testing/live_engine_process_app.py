from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI

from skeleton.api.engine_authority import (
    EngineAuthorityRegistry,
    EngineServiceGrant,
)
from skeleton.api.engine_routes import (
    _engine_coordinator,
    _engine_service,
    _engine_service_token,
    router,
)
from skeleton.api.engine_service import (
    EngineExecutionService,
    SQLiteEngineSubmissionStore,
)
from skeleton.persistence.execution_repository import SQLiteExecutionRepository


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(name + " is required")
    return value


def create_app() -> FastAPI:
    execution_path = Path(_required_env("TEST_ENGINE_EXECUTION_PATH"))
    submission_path = Path(_required_env("TEST_ENGINE_SUBMISSION_PATH"))
    token = _required_env("TEST_ENGINE_SERVICE_TOKEN")

    execution_path.parent.mkdir(parents=True, exist_ok=True)
    submission_path.parent.mkdir(parents=True, exist_ok=True)

    authorities = EngineAuthorityRegistry(
        [
            EngineServiceGrant(
                service_principal="codedock-backend",
                scopes=frozenset(
                    {
                        "engine:submit",
                        "engine:read",
                        "engine:cancel",
                        "engine:events",
                        "engine:approve",
                    }
                ),
                tenant_ids=frozenset({"tenant-a"}),
                capabilities=frozenset({"assistant.chat"}),
            )
        ]
    )
    service = EngineExecutionService(
        SQLiteExecutionRepository(execution_path),
        SQLiteEngineSubmissionStore(submission_path),
        authorities,
    )

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[_engine_service] = lambda: service
    app.dependency_overrides[_engine_service_token] = lambda: token
    app.dependency_overrides[_engine_coordinator] = lambda: None

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI

from skeleton.api.engine_authority import (
    EngineAuthorityRegistry,
    EngineServiceGrant,
)
from skeleton.api.engine_routes import (
    _engine_coordinator,
    _engine_service,
    _engine_service_token,
    router,
)
from skeleton.api.engine_service import (
    EngineExecutionService,
    SQLiteEngineSubmissionStore,
)
from skeleton.persistence.execution_repository import SQLiteExecutionRepository


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(name + " is required")
    return value


def create_app() -> FastAPI:
    execution_path = Path(_required_env("TEST_ENGINE_EXECUTION_PATH"))
    submission_path = Path(_required_env("TEST_ENGINE_SUBMISSION_PATH"))
    token = _required_env("TEST_ENGINE_SERVICE_TOKEN")

    execution_path.parent.mkdir(parents=True, exist_ok=True)
    submission_path.parent.mkdir(parents=True, exist_ok=True)

    authorities = EngineAuthorityRegistry(
        [
            EngineServiceGrant(
                service_principal="codedock-backend",
                scopes=frozenset(
                    {
                        "engine:submit",
                        "engine:read",
                        "engine:cancel",
                        "engine:events",
                        "engine:approve",
                    }
                ),
                tenant_ids=frozenset({"tenant-a"}),
                capabilities=frozenset({"assistant.chat"}),
            )
        ]
    )
    service = EngineExecutionService(
        SQLiteExecutionRepository(execution_path),
        SQLiteEngineSubmissionStore(submission_path),
        authorities,
    )

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[_engine_service] = lambda: service
    app.dependency_overrides[_engine_service_token] = lambda: token
    app.dependency_overrides[_engine_coordinator] = lambda: None

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app
