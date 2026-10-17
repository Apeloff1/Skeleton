"""Ports (interfaces) for app foundation services.

Adapters in this package implement these Protocols.  Callers (Backend HTTP
handlers, Middleware gates, Walt's realtime hub) depend only on the ports.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Protocol, Sequence, runtime_checkable


@dataclass(frozen=True)
class User:
    user_id: str
    email: str
    display_name: str
    created_at: float
    disabled: bool = False


@dataclass(frozen=True)
class SessionPrincipal:
    """What a gate learns about a session.  Never carries the token."""

    session_id: str
    user_id: str
    scopes: tuple[str, ...]
    expires_at: float


@dataclass(frozen=True)
class Project:
    project_id: str
    owner_id: str
    name: str
    created_at: float
    updated_at: float
    settings: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Build:
    build_id: str
    project_id: str
    status: str
    created_at: float
    updated_at: float
    job_id: Optional[str] = None
    target: str = ""
    result: Mapping[str, Any] = field(default_factory=dict)
    error: str = ""


@dataclass(frozen=True)
class Job:
    job_id: str
    kind: str
    status: str
    payload: Mapping[str, Any]
    attempts: int
    max_attempts: int
    run_after: float
    created_at: float
    updated_at: float
    lease_owner: str = ""
    lease_expires_at: float = 0.0
    correlation_id: str = ""
    progress: float = 0.0
    result: Mapping[str, Any] = field(default_factory=dict)
    error: str = ""


@dataclass(frozen=True)
class Asset:
    asset_id: str
    project_id: str
    name: str
    sha256: str
    size: int
    content_type: str
    created_at: float


@runtime_checkable
class SessionResolver(Protocol):
    """Port consumed by Middleware authN gates."""

    def resolve_session(self, token: str) -> Optional[SessionPrincipal]: ...


@runtime_checkable
class UserRepository(Protocol):
    def create_user(self, email: str, display_name: str, password_hash: str) -> User: ...
    def get_user(self, user_id: str) -> Optional[User]: ...
    def find_by_email(self, email: str) -> Optional[tuple[User, str]]: ...
    def set_password_hash(self, user_id: str, password_hash: str) -> None: ...
    def set_disabled(self, user_id: str, disabled: bool) -> None: ...


@runtime_checkable
class SessionRepository(Protocol):
    def insert(self, session_id: str, user_id: str, token_digest: str,
               scopes: Sequence[str], created_at: float, expires_at: float) -> None: ...
    def by_digest(self, token_digest: str) -> Optional[SessionPrincipal]: ...
    def revoke(self, session_id: str) -> bool: ...
    def revoke_user(self, user_id: str) -> int: ...
    def touch(self, session_id: str, expires_at: float) -> None: ...
    def purge_expired(self, now: float) -> int: ...


@runtime_checkable
class ProjectRepository(Protocol):
    def create_project(self, owner_id: str, name: str,
                       settings: Optional[Mapping[str, Any]] = None) -> Project: ...
    def get_project(self, project_id: str) -> Optional[Project]: ...
    def list_projects(self, owner_id: str) -> list[Project]: ...
    def update_settings(self, project_id: str, settings: Mapping[str, Any]) -> Project: ...


@runtime_checkable
class BuildRepository(Protocol):
    def create_build(self, project_id: str, target: str = "") -> Build: ...
    def get_build(self, build_id: str) -> Optional[Build]: ...
    def list_builds(self, project_id: str, limit: int = 50) -> list[Build]: ...
    def set_status(self, build_id: str, status: str, *, job_id: Optional[str] = None,
                   result: Optional[Mapping[str, Any]] = None, error: str = "") -> Build: ...


@runtime_checkable
class JobQueue(Protocol):
    def enqueue(self, kind: str, payload: Mapping[str, Any], *, max_attempts: int = 3,
                delay_s: float = 0.0, correlation_id: str = "",
                idempotency_key: Optional[str] = None) -> Job: ...
    def claim(self, worker_id: str, *, kinds: Optional[Sequence[str]] = None,
              lease_s: float = 60.0) -> Optional[Job]: ...
    def heartbeat(self, job_id: str, worker_id: str, *, lease_s: float = 60.0,
                  progress: Optional[float] = None) -> bool: ...
    def complete(self, job_id: str, worker_id: str,
                 result: Optional[Mapping[str, Any]] = None) -> Job: ...
    def fail(self, job_id: str, worker_id: str, error: str, *,
             retry_delay_s: float = 5.0) -> Job: ...
    def cancel(self, job_id: str) -> bool: ...
    def get(self, job_id: str) -> Optional[Job]: ...


@runtime_checkable
class AssetStore(Protocol):
    def put(self, project_id: str, name: str, data: bytes,
            content_type: str = "application/octet-stream") -> Asset: ...
    def get(self, asset_id: str) -> Optional[Asset]: ...
    def open_bytes(self, asset_id: str) -> bytes: ...
    def list(self, project_id: str) -> list[Asset]: ...
    def remove(self, asset_id: str) -> bool: ...
