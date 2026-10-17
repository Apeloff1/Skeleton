"""SQLite store for the skeleton.projects.v1 resource (schema v6).

Uses the vendored contract models in ``skeleton.contracts.projects``.  Scope
(actor_id, tenant_id) is always supplied by the caller from the verified
session, never from request bodies.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from skeleton.contracts.projects import (
    Project,
    ProjectBrief,
    ProjectBuildLink,
    ProjectContractError,
    ProjectStatus,
    link_build,
)
from skeleton.persistence.app_foundation.db import Database


class ProjectNameConflict(Exception):
    pass


class BuildLinkConflict(Exception):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class ProjectsV1Store:
    def __init__(self, db: Database) -> None:
        self.db = db

    def _row_to_project(self, c, r) -> Project:
        links = [x["execution_id"] for x in c.execute(
            "SELECT execution_id FROM project_build_links WHERE project_id=? ORDER BY seq",
            (r["project_id"],))]
        brief = json.loads(r["brief_json"] or "{}") or {"title": r["name"]}
        return Project(
            project_id=r["project_id"], actor_id=r["owner_id"], tenant_id=r["tenant_id"],
            brief=ProjectBrief.from_dict(brief), status=ProjectStatus(r["status"]),
            build_ids=tuple(links), created_at=_iso(r["created_at"]), updated_at=_iso(r["updated_at"]))

    def create(self, actor_id: str, tenant_id: str, brief: ProjectBrief,
               idempotency_key: Optional[str] = None) -> tuple[Project, bool]:
        """Returns (project, replayed)."""
        create_key = f"{tenant_id}:{actor_id}:{idempotency_key}" if idempotency_key else None
        now = time.time()
        pid = f"prj_{uuid.uuid4().hex}"
        with self.db.tx() as c:
            if create_key:
                r = c.execute("SELECT * FROM projects WHERE create_key=?", (create_key,)).fetchone()
                if r is not None:
                    return self._row_to_project(c, r), True
            try:
                c.execute(
                    "INSERT INTO projects (project_id, owner_id, name, settings, created_at, updated_at,"
                    " brief, tenant_id, status, brief_json, create_key) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (pid, actor_id, brief.title, "{}", now, now, brief.summary, tenant_id,
                     ProjectStatus.DRAFT.value, json.dumps(brief.as_dict(), sort_keys=True), create_key))
            except sqlite3.IntegrityError as exc:
                # Only UNIQUE(owner_id, name) can fire here (create_key replay handled above).
                raise ProjectNameConflict(brief.title) from exc
            r = c.execute("SELECT * FROM projects WHERE project_id=?", (pid,)).fetchone()
            return self._row_to_project(c, r), False

    def get(self, actor_id: str, tenant_id: str, project_id: str) -> Optional[Project]:
        with self.db.tx() as c:
            r = c.execute("SELECT * FROM projects WHERE project_id=? AND owner_id=? AND tenant_id=?",
                          (project_id, actor_id, tenant_id)).fetchone()
            return self._row_to_project(c, r) if r else None

    def list(self, actor_id: str, tenant_id: str, limit: int = 50,
             cursor: Optional[str] = None) -> tuple[list[Project], Optional[str]]:
        after = 0
        if cursor is not None:
            if not cursor.startswith("r:") or not cursor[2:].isdigit():
                raise ProjectContractError("cursor is invalid")
            after = int(cursor[2:])
        with self.db.tx() as c:
            rows = c.execute(
                "SELECT rowid AS rid, * FROM projects WHERE owner_id=? AND tenant_id=? AND rowid>?"
                " ORDER BY rowid LIMIT ?", (actor_id, tenant_id, after, limit + 1)).fetchall()
            items = [self._row_to_project(c, r) for r in rows[:limit]]
            nxt = f"r:{rows[limit - 1]['rid']}" if len(rows) > limit else None
            return items, nxt

    def link(self, actor_id: str, tenant_id: str, project_id: str,
             execution_id: str) -> Optional[ProjectBuildLink]:
        """Link an execution; None if project not in scope. Raises BuildLinkConflict."""
        with self.db.tx() as c:
            r = c.execute("SELECT * FROM projects WHERE project_id=? AND owner_id=? AND tenant_id=?",
                          (project_id, actor_id, tenant_id)).fetchone()
            if r is None:
                return None
            other = c.execute("SELECT 1 FROM project_build_links WHERE execution_id=? AND tenant_id<>?",
                              (execution_id, tenant_id)).fetchone()
            if other is not None:
                raise BuildLinkConflict(execution_id)
            project = self._row_to_project(c, r)
            now = utc_now()
            try:
                updated, result = link_build(project, execution_id, linked_at=now)
            except ProjectContractError as exc:  # e.g. more than 64 builds
                raise BuildLinkConflict(execution_id) from exc
            if result.replayed:
                prev = c.execute("SELECT linked_at FROM project_build_links WHERE project_id=? AND execution_id=?",
                                 (project_id, execution_id)).fetchone()
                return ProjectBuildLink(project_id, execution_id, prev["linked_at"], replayed=True)
            c.execute("INSERT INTO project_build_links VALUES (?,?,?,?,?)",
                      (project_id, execution_id, tenant_id, len(project.build_ids) + 1, now))
            c.execute("UPDATE projects SET status=?, updated_at=? WHERE project_id=?",
                      (updated.status.value, time.time(), project_id))
            return result
