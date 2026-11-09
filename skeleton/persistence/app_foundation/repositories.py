"""SQLite adapters for UserRepository, SessionRepository, Project/Build repos."""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, Mapping, Optional, Sequence

from skeleton.persistence.app_foundation.db import Database
from skeleton.app_services.ports import Build, Project, SessionPrincipal, User

BUILD_STATUSES = frozenset({"pending", "queued", "running", "succeeded", "failed", "cancelled"})


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


class SqliteUserRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    @staticmethod
    def _user(r: Any) -> User:
        return User(r["user_id"], r["email"], r["display_name"], r["created_at"], bool(r["disabled"]))

    def create_user(self, email: str, display_name: str, password_hash: str) -> User:
        now = time.time()
        uid = _new_id("usr")
        with self.db.tx() as c:
            c.execute("INSERT INTO users VALUES (?,?,?,?,0,?,?)",
                      (uid, email.strip(), display_name, password_hash, now, now))
        return User(uid, email.strip(), display_name, now)

    def get_user(self, user_id: str) -> Optional[User]:
        rows = self.db.query("SELECT * FROM users WHERE user_id=?", (user_id,))
        return self._user(rows[0]) if rows else None

    def find_by_email(self, email: str) -> Optional[tuple[User, str]]:
        rows = self.db.query("SELECT * FROM users WHERE email=?", (email.strip(),))
        return (self._user(rows[0]), rows[0]["password_hash"]) if rows else None

    def set_password_hash(self, user_id: str, password_hash: str) -> None:
        with self.db.tx() as c:
            c.execute("UPDATE users SET password_hash=?, updated_at=? WHERE user_id=?",
                      (password_hash, time.time(), user_id))

    def set_disabled(self, user_id: str, disabled: bool) -> None:
        with self.db.tx() as c:
            c.execute("UPDATE users SET disabled=?, updated_at=? WHERE user_id=?",
                      (int(disabled), time.time(), user_id))


class SqliteSessionRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def insert(self, session_id: str, user_id: str, token_digest: str,
               scopes: Sequence[str], created_at: float, expires_at: float) -> None:
        with self.db.tx() as c:
            c.execute("INSERT INTO sessions VALUES (?,?,?,?,?,?,0)",
                      (session_id, user_id, token_digest, " ".join(scopes), created_at, expires_at))

    def by_digest(self, token_digest: str) -> Optional[SessionPrincipal]:
        rows = self.db.query(
            "SELECT s.* FROM sessions s JOIN users u USING(user_id) "
            "WHERE s.token_digest=? AND s.revoked=0 AND u.disabled=0", (token_digest,))
        if not rows:
            return None
        r = rows[0]
        return SessionPrincipal(r["session_id"], r["user_id"],
                                tuple(x for x in r["scopes"].split(" ") if x), r["expires_at"])

    def revoke(self, session_id: str) -> bool:
        with self.db.tx() as c:
            return c.execute("UPDATE sessions SET revoked=1 WHERE session_id=? AND revoked=0",
                             (session_id,)).rowcount > 0

    def revoke_user(self, user_id: str) -> int:
        with self.db.tx() as c:
            return c.execute("UPDATE sessions SET revoked=1 WHERE user_id=? AND revoked=0",
                             (user_id,)).rowcount

    def touch(self, session_id: str, expires_at: float) -> None:
        with self.db.tx() as c:
            c.execute("UPDATE sessions SET expires_at=? WHERE session_id=?", (expires_at, session_id))

    def purge_expired(self, now: float) -> int:
        with self.db.tx() as c:
            return c.execute("DELETE FROM sessions WHERE expires_at<? OR revoked=1", (now,)).rowcount


class SqliteProjectRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    @staticmethod
    def _p(r: Any) -> Project:
        return Project(r["project_id"], r["owner_id"], r["name"], r["created_at"],
                       r["updated_at"], json.loads(r["settings"]), r["brief"])

    def create_project(self, owner_id: str, name: str,
                       settings: Optional[Mapping[str, Any]] = None, brief: str = "") -> Project:
        if not name.strip():
            raise ValueError("project name required")
        now = time.time()
        pid = _new_id("prj")
        with self.db.tx() as c:
            c.execute("INSERT INTO projects (project_id, owner_id, name, settings, created_at, updated_at, brief)"
                      " VALUES (?,?,?,?,?,?,?)",
                      (pid, owner_id, name.strip(), json.dumps(dict(settings or {}), sort_keys=True), now, now, brief))
        return self.get_project(pid)  # type: ignore[return-value]

    def get_project(self, project_id: str) -> Optional[Project]:
        rows = self.db.query("SELECT * FROM projects WHERE project_id=?", (project_id,))
        return self._p(rows[0]) if rows else None

    def list_projects(self, owner_id: str) -> list[Project]:
        return [self._p(r) for r in self.db.query(
            "SELECT * FROM projects WHERE owner_id=? ORDER BY created_at", (owner_id,))]

    def update_settings(self, project_id: str, settings: Mapping[str, Any]) -> Project:
        with self.db.tx() as c:
            if c.execute("UPDATE projects SET settings=?, updated_at=? WHERE project_id=?",
                         (json.dumps(dict(settings), sort_keys=True), time.time(), project_id)).rowcount == 0:
                raise KeyError(project_id)
        return self.get_project(project_id)  # type: ignore[return-value]


class SqliteBuildRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    @staticmethod
    def _b(r: Any) -> Build:
        return Build(r["build_id"], r["project_id"], r["status"], r["created_at"], r["updated_at"],
                     r["job_id"], r["target"], json.loads(r["result"]), r["error"])

    def create_build(self, project_id: str, target: str = "", *,
                     job_id: Optional[str] = None, transaction: Any = None) -> Build:
        """Create a build, optionally in the existing queue publication transaction."""
        now = time.time()
        bid = _new_id("bld")
        def insert(c):
            c.execute("INSERT INTO builds (build_id, project_id, status, target, job_id, created_at, updated_at)"
                      " VALUES (?,?,?,?,?,?,?)",
                      (bid, project_id, "queued" if job_id else "pending", target, job_id, now, now))
            return self._b(c.execute("SELECT * FROM builds WHERE build_id=?", (bid,)).fetchone())
        if transaction is not None:
            return insert(transaction)
        with self.db.tx() as c:
            return insert(c)

    def get_build(self, build_id: str) -> Optional[Build]:
        rows = self.db.query("SELECT * FROM builds WHERE build_id=?", (build_id,))
        return self._b(rows[0]) if rows else None

    def list_builds(self, project_id: str, limit: int = 50) -> list[Build]:
        return [self._b(r) for r in self.db.query(
            "SELECT * FROM builds WHERE project_id=? ORDER BY created_at DESC LIMIT ?",
            (project_id, int(limit)))]

    def set_status(self, build_id: str, status: str, *, job_id: Optional[str] = None,
                   result: Optional[Mapping[str, Any]] = None, error: str = "") -> Build:
        if status not in BUILD_STATUSES:
            raise ValueError(f"invalid build status {status!r}")
        sets, args = ["status=?", "updated_at=?", "error=?"], [status, time.time(), error]
        if job_id is not None:
            sets.append("job_id=?")
            args.append(job_id)
        if result is not None:
            sets.append("result=?")
            args.append(json.dumps(dict(result), sort_keys=True))
        with self.db.tx() as c:
            if c.execute(f"UPDATE builds SET {', '.join(sets)} WHERE build_id=?",
                         (*args, build_id)).rowcount == 0:
                raise KeyError(build_id)
        return self.get_build(build_id)  # type: ignore[return-value]
