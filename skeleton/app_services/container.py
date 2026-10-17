"""Composition root for app foundation services (no HTTP, no lifespan hooks).

Backend can construct this from its own lifespan without touching
``api/server.py``: ``AppServices.open(data_dir)``.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from skeleton.app_services.assets import LocalAssetStore
from skeleton.app_services.auth import AuthService
from skeleton.persistence.app_foundation.db import Database
from skeleton.app_services.events import EventBusBridge, FanOutPublisher
from skeleton.app_services.jobs import BuildExecutor, BuildJobRunner, BuildService, SqliteJobQueue
from skeleton.persistence.app_foundation.repositories import (
    SqliteBuildRepository,
    SqliteProjectRepository,
    SqliteSessionRepository,
    SqliteUserRepository,
)


@dataclass
class AppServices:
    db: Database
    auth: AuthService
    projects: SqliteProjectRepository
    builds: SqliteBuildRepository
    queue: SqliteJobQueue
    build_service: BuildService
    assets: LocalAssetStore
    events: FanOutPublisher

    @classmethod
    def open(cls, data_dir: str | Path, *, in_memory: bool = False,
             event_bus: Optional[object] = None) -> "AppServices":
        data_dir = Path(data_dir)
        db = Database(":memory:" if in_memory else data_dir / "app.sqlite3")
        db.migrate()
        events = FanOutPublisher()
        if event_bus is not None:
            events.subscribe(EventBusBridge(event_bus))
        builds = SqliteBuildRepository(db)
        queue = SqliteJobQueue(db)
        return cls(db=db,
                   auth=AuthService(SqliteUserRepository(db), SqliteSessionRepository(db)),
                   projects=SqliteProjectRepository(db), builds=builds, queue=queue,
                   build_service=BuildService(builds, queue),
                   assets=LocalAssetStore(db, data_dir / "assets"), events=events)

    def build_runner(self, executor: BuildExecutor, **kw) -> BuildJobRunner:
        return BuildJobRunner(self.queue, self.builds, executor, publisher=self.events, **kw)

    def close(self) -> None:
        self.db.close()
