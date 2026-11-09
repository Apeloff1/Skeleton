"""Durable agent lifecycle, checkpoint, and resource-accounting authority.

This module closes the gap between delegation qualification and runtime
lifecycle ownership. It does not execute model/tool work. Instead it provides a
small deterministic supervisor that:

* binds an agent descriptor to an already-qualified delegation authority,
* persists append-only lifecycle checkpoints,
* fences concurrent/stale state transitions with a digest chain,
* accounts task concurrency, steps, tokens, cost, and wall time, and
* restores the exact last durable state after process restart.

The store deliberately persists only bounded agent metadata and accounting
state. Task payloads, prompts, model outputs, and secrets are never stored here.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import threading
from time import time
from typing import Any, Iterable, Mapping

from skeleton.automation.agents.delegation_qualification import (
    AgentDelegationAuthority,
    DelegationBudget,
)


AGENT_RUNTIME_SCHEMA_VERSION = 1
_MAX_ITEMS = 256
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
_ZERO_DIGEST = "0" * 64


class AgentRuntimeError(RuntimeError):
    """Base durable agent runtime failure."""


class AgentRuntimeConflict(AgentRuntimeError):
    """Durable state changed or identity was reused incompatibly."""


class AgentRuntimeDenied(AgentRuntimeError):
    """A requested lifecycle/resource transition is not authorized."""


class AgentLifecycleState(str, Enum):
    REGISTERED = "registered"
    RUNNING = "running"
    SUSPENDED = "suspended"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


_TERMINAL_STATES = frozenset(
    {
        AgentLifecycleState.COMPLETED,
        AgentLifecycleState.FAILED,
        AgentLifecycleState.CANCELLED,
    }
)


def _token(value: object, field: str) -> str:
    if not isinstance(value, str) or not _TOKEN_RE.fullmatch(value):
        raise AgentRuntimeError(f"{field} must be a canonical token")
    return value


def _tokens(values: Iterable[str], field: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise AgentRuntimeError(f"{field} must be an iterable")
    normalized: set[str] = set()
    for raw in values:
        normalized.add(_token(raw, field))
        if len(normalized) > _MAX_ITEMS:
            raise AgentRuntimeError(f"{field} exceeds item limit")
    if not normalized and not allow_empty:
        raise AgentRuntimeError(f"{field} must be non-empty")
    return tuple(sorted(normalized))


def _finite_non_negative(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AgentRuntimeError(f"{field} must be finite non-negative numeric")
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise AgentRuntimeError(f"{field} must be finite non-negative numeric")
    return result


def _non_negative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise AgentRuntimeError(f"{field} must be a non-negative integer")
    return value


def _positive_int(value: object, field: str) -> int:
    result = _non_negative_int(value, field)
    if result < 1:
        raise AgentRuntimeError(f"{field} must be a positive integer")
    return result


def _digest(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise AgentRuntimeError(f"{field} must be lowercase sha256")
    return value


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise AgentRuntimeError("agent runtime value is not canonical JSON") from exc


def _canonical_digest(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class AgentDescriptor:
    """Static identity and outer resource envelope for one runtime agent."""

    agent_id: str
    role: str
    objective_scopes: tuple[str, ...]
    capabilities: tuple[str, ...]
    memory_policy: str
    budget: DelegationBudget
    schema_version: int = AGENT_RUNTIME_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "agent_id", _token(self.agent_id, "agent_id"))
        object.__setattr__(self, "role", _token(self.role, "role"))
        object.__setattr__(
            self,
            "objective_scopes",
            _tokens(self.objective_scopes, "objective_scopes"),
        )
        object.__setattr__(
            self,
            "capabilities",
            _tokens(self.capabilities, "capabilities"),
        )
        object.__setattr__(
            self,
            "memory_policy",
            _token(self.memory_policy, "memory_policy"),
        )
        if not isinstance(self.budget, DelegationBudget):
            raise AgentRuntimeError("budget must be DelegationBudget")
        if self.schema_version != AGENT_RUNTIME_SCHEMA_VERSION:
            raise AgentRuntimeError("unsupported agent runtime schema version")

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "agent_id": self.agent_id,
            "role": self.role,
            "objective_scopes": list(self.objective_scopes),
            "capabilities": list(self.capabilities),
            "memory_policy": self.memory_policy,
            "budget": self.budget.payload(),
        }

    @property
    def digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class AgentResourceUsage:
    """Cumulative metered usage; active concurrency is checkpoint-owned."""

    steps: int = 0
    tokens: int = 0
    cost_units: float = 0.0
    wall_time_s: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "steps", _non_negative_int(self.steps, "steps"))
        object.__setattr__(self, "tokens", _non_negative_int(self.tokens, "tokens"))
        object.__setattr__(
            self,
            "cost_units",
            _finite_non_negative(self.cost_units, "cost_units"),
        )
        object.__setattr__(
            self,
            "wall_time_s",
            _finite_non_negative(self.wall_time_s, "wall_time_s"),
        )

    def add(
        self,
        *,
        steps: int = 0,
        tokens: int = 0,
        cost_units: float = 0.0,
        wall_time_s: float = 0.0,
    ) -> "AgentResourceUsage":
        return AgentResourceUsage(
            steps=self.steps + _non_negative_int(steps, "steps"),
            tokens=self.tokens + _non_negative_int(tokens, "tokens"),
            cost_units=self.cost_units
            + _finite_non_negative(cost_units, "cost_units"),
            wall_time_s=self.wall_time_s
            + _finite_non_negative(wall_time_s, "wall_time_s"),
        )

    def within(self, budget: DelegationBudget) -> bool:
        if not isinstance(budget, DelegationBudget):
            raise TypeError("budget must be DelegationBudget")
        return (
            self.steps <= budget.max_steps
            and self.tokens <= budget.max_tokens
            and self.cost_units <= budget.max_cost_units
            and self.wall_time_s <= budget.max_wall_time_s
        )

    def payload(self) -> dict[str, Any]:
        return {
            "steps": self.steps,
            "tokens": self.tokens,
            "cost_units": self.cost_units,
            "wall_time_s": self.wall_time_s,
        }


@dataclass(frozen=True, slots=True)
class AgentCheckpoint:
    """One append-only lifecycle/resource checkpoint."""

    tenant_id: str
    agent_id: str
    sequence: int
    state: AgentLifecycleState
    descriptor_digest: str
    authority_digest: str
    usage: AgentResourceUsage
    active_task_ids: tuple[str, ...]
    reason: str | None
    created_at: float
    previous_digest: str
    checkpoint_digest: str
    schema_version: int = AGENT_RUNTIME_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "tenant_id", _token(self.tenant_id, "tenant_id"))
        object.__setattr__(self, "agent_id", _token(self.agent_id, "agent_id"))
        object.__setattr__(self, "sequence", _positive_int(self.sequence, "sequence"))
        try:
            object.__setattr__(self, "state", AgentLifecycleState(self.state))
        except ValueError as exc:
            raise AgentRuntimeError("invalid agent lifecycle state") from exc
        _digest(self.descriptor_digest, "descriptor_digest")
        _digest(self.authority_digest, "authority_digest")
        if not isinstance(self.usage, AgentResourceUsage):
            raise AgentRuntimeError("usage must be AgentResourceUsage")
        object.__setattr__(
            self,
            "active_task_ids",
            _tokens(self.active_task_ids, "active_task_ids", allow_empty=True),
        )
        if self.reason is not None:
            object.__setattr__(self, "reason", _token(self.reason, "reason"))
        object.__setattr__(
            self,
            "created_at",
            _finite_non_negative(self.created_at, "created_at"),
        )
        _digest(self.previous_digest, "previous_digest")
        _digest(self.checkpoint_digest, "checkpoint_digest")
        if self.schema_version != AGENT_RUNTIME_SCHEMA_VERSION:
            raise AgentRuntimeError("unsupported agent runtime schema version")
        if self.state in _TERMINAL_STATES and self.active_task_ids:
            raise AgentRuntimeError("terminal checkpoint cannot retain active tasks")
        expected = _canonical_digest(self.identity_payload())
        if expected != self.checkpoint_digest:
            raise AgentRuntimeError("checkpoint digest mismatch")

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "tenant_id": self.tenant_id,
            "agent_id": self.agent_id,
            "sequence": self.sequence,
            "state": self.state.value,
            "descriptor_digest": self.descriptor_digest,
            "authority_digest": self.authority_digest,
            "usage": self.usage.payload(),
            "active_task_ids": list(self.active_task_ids),
            "reason": self.reason,
            "created_at": self.created_at,
            "previous_digest": self.previous_digest,
        }

    def payload(self) -> dict[str, Any]:
        return {
            **self.identity_payload(),
            "checkpoint_digest": self.checkpoint_digest,
        }


def _checkpoint(
    *,
    tenant_id: str,
    agent_id: str,
    sequence: int,
    state: AgentLifecycleState,
    descriptor_digest: str,
    authority_digest: str,
    usage: AgentResourceUsage,
    active_task_ids: Iterable[str],
    reason: str | None,
    created_at: float,
    previous_digest: str,
) -> AgentCheckpoint:
    identity = {
        "schema_version": AGENT_RUNTIME_SCHEMA_VERSION,
        "tenant_id": _token(tenant_id, "tenant_id"),
        "agent_id": _token(agent_id, "agent_id"),
        "sequence": _positive_int(sequence, "sequence"),
        "state": AgentLifecycleState(state).value,
        "descriptor_digest": _digest(descriptor_digest, "descriptor_digest"),
        "authority_digest": _digest(authority_digest, "authority_digest"),
        "usage": usage.payload(),
        "active_task_ids": list(
            _tokens(active_task_ids, "active_task_ids", allow_empty=True)
        ),
        "reason": None if reason is None else _token(reason, "reason"),
        "created_at": _finite_non_negative(created_at, "created_at"),
        "previous_digest": _digest(previous_digest, "previous_digest"),
    }
    return AgentCheckpoint(
        tenant_id=str(identity["tenant_id"]),
        agent_id=str(identity["agent_id"]),
        sequence=int(identity["sequence"]),
        state=AgentLifecycleState(str(identity["state"])),
        descriptor_digest=str(identity["descriptor_digest"]),
        authority_digest=str(identity["authority_digest"]),
        usage=usage,
        active_task_ids=tuple(identity["active_task_ids"]),
        reason=identity["reason"],
        created_at=float(identity["created_at"]),
        previous_digest=str(identity["previous_digest"]),
        checkpoint_digest=_canonical_digest(identity),
        schema_version=AGENT_RUNTIME_SCHEMA_VERSION,
    )


def _budget_from_payload(payload: Mapping[str, object]) -> DelegationBudget:
    return DelegationBudget(
        max_parallel_tasks=int(payload["max_parallel_tasks"]),
        max_steps=int(payload["max_steps"]),
        max_tokens=int(payload["max_tokens"]),
        max_cost_units=float(payload["max_cost_units"]),
        max_wall_time_s=float(payload["max_wall_time_s"]),
    )


def _descriptor_from_json(raw: str) -> AgentDescriptor:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AgentRuntimeError("descriptor JSON is invalid") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("budget"), dict):
        raise AgentRuntimeError("descriptor JSON is invalid")
    return AgentDescriptor(
        agent_id=str(payload["agent_id"]),
        role=str(payload["role"]),
        objective_scopes=tuple(payload["objective_scopes"]),
        capabilities=tuple(payload["capabilities"]),
        memory_policy=str(payload["memory_policy"]),
        budget=_budget_from_payload(payload["budget"]),
        schema_version=int(payload.get("schema_version", 1)),
    )


def _authority_from_json(raw: str) -> AgentDelegationAuthority:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AgentRuntimeError("authority JSON is invalid") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("budget"), dict):
        raise AgentRuntimeError("authority JSON is invalid")
    return AgentDelegationAuthority(
        agent_id=str(payload["agent_id"]),
        parent_agent_id=(
            None
            if payload.get("parent_agent_id") is None
            else str(payload["parent_agent_id"])
        ),
        generation=int(payload["generation"]),
        capabilities=tuple(payload["capabilities"]),
        scopes=tuple(payload["scopes"]),
        budget=_budget_from_payload(payload["budget"]),
        expires_at=float(payload["expires_at"]),
        delegation_id=str(payload["delegation_id"]),
    )


def _checkpoint_from_json(raw: str) -> AgentCheckpoint:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AgentRuntimeError("checkpoint JSON is invalid") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("usage"), dict):
        raise AgentRuntimeError("checkpoint JSON is invalid")
    usage = payload["usage"]
    return AgentCheckpoint(
        tenant_id=str(payload["tenant_id"]),
        agent_id=str(payload["agent_id"]),
        sequence=int(payload["sequence"]),
        state=AgentLifecycleState(str(payload["state"])),
        descriptor_digest=str(payload["descriptor_digest"]),
        authority_digest=str(payload["authority_digest"]),
        usage=AgentResourceUsage(
            steps=int(usage["steps"]),
            tokens=int(usage["tokens"]),
            cost_units=float(usage["cost_units"]),
            wall_time_s=float(usage["wall_time_s"]),
        ),
        active_task_ids=tuple(payload.get("active_task_ids", ())),
        reason=payload.get("reason"),
        created_at=float(payload["created_at"]),
        previous_digest=str(payload["previous_digest"]),
        checkpoint_digest=str(payload["checkpoint_digest"]),
        schema_version=int(payload.get("schema_version", 1)),
    )


class SQLiteAgentRuntimeStore:
    """Append-only durable agent registration/checkpoint authority."""

    def __init__(
        self,
        path: str | Path = ":memory:",
        *,
        namespace: str = "agent_runtime",
    ) -> None:
        self.namespace = _token(str(namespace), "namespace")
        self._connection = sqlite3.connect(
            str(path),
            check_same_thread=False,
            isolation_level=None,
            timeout=5.0,
        )
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS agent_runtime_registration (
                    namespace TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    descriptor_json TEXT NOT NULL,
                    authority_json TEXT NOT NULL,
                    descriptor_digest TEXT NOT NULL,
                    authority_digest TEXT NOT NULL,
                    registered_at REAL NOT NULL,
                    PRIMARY KEY(namespace, tenant_id, agent_id)
                );

                CREATE TABLE IF NOT EXISTS agent_runtime_checkpoint (
                    namespace TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    checkpoint_json TEXT NOT NULL,
                    checkpoint_digest TEXT NOT NULL,
                    previous_digest TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    PRIMARY KEY(namespace, tenant_id, agent_id, sequence),
                    UNIQUE(namespace, checkpoint_digest)
                );

                CREATE INDEX IF NOT EXISTS idx_agent_runtime_checkpoint_latest
                ON agent_runtime_checkpoint(
                    namespace, tenant_id, agent_id, sequence DESC
                );
                """
            )

    def register(
        self,
        tenant_id: str,
        descriptor: AgentDescriptor,
        authority: AgentDelegationAuthority,
        *,
        now: float,
    ) -> None:
        tenant = _token(tenant_id, "tenant_id")
        if not isinstance(descriptor, AgentDescriptor):
            raise TypeError("descriptor must be AgentDescriptor")
        if not isinstance(authority, AgentDelegationAuthority):
            raise TypeError("authority must be AgentDelegationAuthority")
        instant = _finite_non_negative(now, "now")
        descriptor_json = _canonical_json(descriptor.payload())
        authority_json = _canonical_json(authority.payload())
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._connection.execute(
                    """
                    SELECT * FROM agent_runtime_registration
                    WHERE namespace = ? AND tenant_id = ? AND agent_id = ?
                    """,
                    (self.namespace, tenant, descriptor.agent_id),
                ).fetchone()
                if row is None:
                    self._connection.execute(
                        """
                        INSERT INTO agent_runtime_registration(
                            namespace, tenant_id, agent_id,
                            descriptor_json, authority_json,
                            descriptor_digest, authority_digest, registered_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            self.namespace,
                            tenant,
                            descriptor.agent_id,
                            descriptor_json,
                            authority_json,
                            descriptor.digest,
                            authority.digest,
                            instant,
                        ),
                    )
                elif (
                    row["descriptor_digest"] != descriptor.digest
                    or row["authority_digest"] != authority.digest
                    or row["descriptor_json"] != descriptor_json
                    or row["authority_json"] != authority_json
                ):
                    raise AgentRuntimeConflict(
                        "agent identity already registered with different contract"
                    )
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def registration(
        self,
        tenant_id: str,
        agent_id: str,
    ) -> tuple[AgentDescriptor, AgentDelegationAuthority] | None:
        tenant = _token(tenant_id, "tenant_id")
        agent = _token(agent_id, "agent_id")
        with self._lock:
            row = self._connection.execute(
                """
                SELECT * FROM agent_runtime_registration
                WHERE namespace = ? AND tenant_id = ? AND agent_id = ?
                """,
                (self.namespace, tenant, agent),
            ).fetchone()
        if row is None:
            return None
        descriptor = _descriptor_from_json(str(row["descriptor_json"]))
        authority = _authority_from_json(str(row["authority_json"]))
        if (
            descriptor.digest != row["descriptor_digest"]
            or authority.digest != row["authority_digest"]
        ):
            raise AgentRuntimeConflict("durable agent registration digest mismatch")
        return descriptor, authority

    def append(self, checkpoint: AgentCheckpoint) -> AgentCheckpoint:
        if not isinstance(checkpoint, AgentCheckpoint):
            raise TypeError("checkpoint must be AgentCheckpoint")
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                registration = self._connection.execute(
                    """
                    SELECT descriptor_digest, authority_digest
                    FROM agent_runtime_registration
                    WHERE namespace = ? AND tenant_id = ? AND agent_id = ?
                    """,
                    (
                        self.namespace,
                        checkpoint.tenant_id,
                        checkpoint.agent_id,
                    ),
                ).fetchone()
                if registration is None:
                    raise AgentRuntimeConflict(
                        "checkpoint cannot append before registration"
                    )
                if (
                    registration["descriptor_digest"]
                    != checkpoint.descriptor_digest
                    or registration["authority_digest"]
                    != checkpoint.authority_digest
                ):
                    raise AgentRuntimeConflict(
                        "checkpoint registration identity drift"
                    )

                latest = self._connection.execute(
                    """
                    SELECT sequence, checkpoint_digest
                    FROM agent_runtime_checkpoint
                    WHERE namespace = ? AND tenant_id = ? AND agent_id = ?
                    ORDER BY sequence DESC LIMIT 1
                    """,
                    (
                        self.namespace,
                        checkpoint.tenant_id,
                        checkpoint.agent_id,
                    ),
                ).fetchone()
                expected_sequence = 1 if latest is None else int(latest["sequence"]) + 1
                expected_previous = (
                    _ZERO_DIGEST
                    if latest is None
                    else str(latest["checkpoint_digest"])
                )
                if checkpoint.sequence != expected_sequence:
                    raise AgentRuntimeConflict(
                        "checkpoint sequence changed before append"
                    )
                if checkpoint.previous_digest != expected_previous:
                    raise AgentRuntimeConflict(
                        "checkpoint chain changed before append"
                    )
                self._connection.execute(
                    """
                    INSERT INTO agent_runtime_checkpoint(
                        namespace, tenant_id, agent_id, sequence,
                        checkpoint_json, checkpoint_digest,
                        previous_digest, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        self.namespace,
                        checkpoint.tenant_id,
                        checkpoint.agent_id,
                        checkpoint.sequence,
                        _canonical_json(checkpoint.payload()),
                        checkpoint.checkpoint_digest,
                        checkpoint.previous_digest,
                        checkpoint.created_at,
                    ),
                )
                self._connection.execute("COMMIT")
                return checkpoint
            except sqlite3.IntegrityError as exc:
                self._connection.execute("ROLLBACK")
                raise AgentRuntimeConflict(
                    "checkpoint append collided with concurrent writer"
                ) from exc
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def history(
        self,
        tenant_id: str,
        agent_id: str,
    ) -> tuple[AgentCheckpoint, ...]:
        tenant = _token(tenant_id, "tenant_id")
        agent = _token(agent_id, "agent_id")
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT checkpoint_json
                FROM agent_runtime_checkpoint
                WHERE namespace = ? AND tenant_id = ? AND agent_id = ?
                ORDER BY sequence ASC
                """,
                (self.namespace, tenant, agent),
            ).fetchall()
        checkpoints = tuple(
            _checkpoint_from_json(str(row["checkpoint_json"]))
            for row in rows
        )
        previous = _ZERO_DIGEST
        for index, checkpoint in enumerate(checkpoints, start=1):
            if checkpoint.sequence != index:
                raise AgentRuntimeConflict("durable checkpoint sequence gap")
            if checkpoint.previous_digest != previous:
                raise AgentRuntimeConflict("durable checkpoint chain mismatch")
            previous = checkpoint.checkpoint_digest
        return checkpoints

    def latest(
        self,
        tenant_id: str,
        agent_id: str,
    ) -> AgentCheckpoint | None:
        history = self.history(tenant_id, agent_id)
        return None if not history else history[-1]

    def close(self) -> None:
        with self._lock:
            self._connection.close()


class DurableAgentSupervisor:
    """Lifecycle and resource authority for one durable agent namespace."""

    def __init__(
        self,
        store: SQLiteAgentRuntimeStore,
        *,
        clock=time,
    ) -> None:
        if not isinstance(store, SQLiteAgentRuntimeStore):
            raise TypeError("store must be SQLiteAgentRuntimeStore")
        if not callable(clock):
            raise TypeError("clock must be callable")
        self.store = store
        self._clock = clock

    @staticmethod
    def _validate_binding(
        descriptor: AgentDescriptor,
        authority: AgentDelegationAuthority,
    ) -> None:
        if authority.agent_id != descriptor.agent_id:
            raise AgentRuntimeDenied(
                "delegation authority agent does not match descriptor"
            )
        if not set(authority.capabilities).issubset(descriptor.capabilities):
            raise AgentRuntimeDenied(
                "delegation authority exceeds descriptor capabilities"
            )
        if not set(authority.scopes).issubset(descriptor.objective_scopes):
            raise AgentRuntimeDenied(
                "delegation authority exceeds descriptor objective scopes"
            )
        if not authority.budget.within(descriptor.budget):
            raise AgentRuntimeDenied(
                "delegation authority exceeds descriptor resource budget"
            )

    def _now(self) -> float:
        return _finite_non_negative(self._clock(), "clock")

    def register(
        self,
        tenant_id: str,
        descriptor: AgentDescriptor,
        authority: AgentDelegationAuthority,
    ) -> AgentCheckpoint:
        self._validate_binding(descriptor, authority)
        now = self._now()
        if now >= authority.expires_at:
            raise AgentRuntimeDenied("delegation authority is expired")
        self.store.register(
            tenant_id,
            descriptor,
            authority,
            now=now,
        )
        latest = self.store.latest(tenant_id, descriptor.agent_id)
        if latest is not None:
            return latest
        checkpoint = _checkpoint(
            tenant_id=tenant_id,
            agent_id=descriptor.agent_id,
            sequence=1,
            state=AgentLifecycleState.REGISTERED,
            descriptor_digest=descriptor.digest,
            authority_digest=authority.digest,
            usage=AgentResourceUsage(),
            active_task_ids=(),
            reason="registered",
            created_at=now,
            previous_digest=_ZERO_DIGEST,
        )
        return self.store.append(checkpoint)

    def _load(
        self,
        tenant_id: str,
        agent_id: str,
    ) -> tuple[AgentDescriptor, AgentDelegationAuthority, AgentCheckpoint]:
        registration = self.store.registration(tenant_id, agent_id)
        if registration is None:
            raise AgentRuntimeConflict("agent is not registered")
        descriptor, authority = registration
        self._validate_binding(descriptor, authority)
        latest = self.store.latest(tenant_id, agent_id)
        if latest is None:
            raise AgentRuntimeConflict("registered agent has no checkpoint")
        if (
            latest.descriptor_digest != descriptor.digest
            or latest.authority_digest != authority.digest
        ):
            raise AgentRuntimeConflict("latest checkpoint identity drift")
        return descriptor, authority, latest

    def checkpoint(
        self,
        tenant_id: str,
        agent_id: str,
    ) -> AgentCheckpoint:
        return self._load(tenant_id, agent_id)[2]

    def history(
        self,
        tenant_id: str,
        agent_id: str,
    ) -> tuple[AgentCheckpoint, ...]:
        self._load(tenant_id, agent_id)
        return self.store.history(tenant_id, agent_id)

    def _append(
        self,
        tenant_id: str,
        descriptor: AgentDescriptor,
        authority: AgentDelegationAuthority,
        previous: AgentCheckpoint,
        *,
        state: AgentLifecycleState | None = None,
        usage: AgentResourceUsage | None = None,
        active_task_ids: Iterable[str] | None = None,
        reason: str | None = None,
        require_live_authority: bool = False,
    ) -> AgentCheckpoint:
        now = self._now()
        if require_live_authority and now >= authority.expires_at:
            raise AgentRuntimeDenied("delegation authority is expired")
        checkpoint = _checkpoint(
            tenant_id=tenant_id,
            agent_id=descriptor.agent_id,
            sequence=previous.sequence + 1,
            state=previous.state if state is None else state,
            descriptor_digest=descriptor.digest,
            authority_digest=authority.digest,
            usage=previous.usage if usage is None else usage,
            active_task_ids=(
                previous.active_task_ids
                if active_task_ids is None
                else active_task_ids
            ),
            reason=reason,
            created_at=now,
            previous_digest=previous.checkpoint_digest,
        )
        return self.store.append(checkpoint)

    def start(self, tenant_id: str, agent_id: str) -> AgentCheckpoint:
        descriptor, authority, current = self._load(tenant_id, agent_id)
        if current.state not in {
            AgentLifecycleState.REGISTERED,
            AgentLifecycleState.SUSPENDED,
        }:
            raise AgentRuntimeDenied(
                f"agent cannot start from {current.state.value}"
            )
        return self._append(
            tenant_id,
            descriptor,
            authority,
            current,
            state=AgentLifecycleState.RUNNING,
            reason="started",
            require_live_authority=True,
        )

    def suspend(self, tenant_id: str, agent_id: str) -> AgentCheckpoint:
        descriptor, authority, current = self._load(tenant_id, agent_id)
        if current.state is not AgentLifecycleState.RUNNING:
            raise AgentRuntimeDenied("only a running agent may suspend")
        if current.active_task_ids:
            raise AgentRuntimeDenied(
                "agent cannot suspend while tasks are active"
            )
        return self._append(
            tenant_id,
            descriptor,
            authority,
            current,
            state=AgentLifecycleState.SUSPENDED,
            reason="suspended",
        )

    def cancel(
        self,
        tenant_id: str,
        agent_id: str,
        *,
        reason: str = "cancelled",
    ) -> AgentCheckpoint:
        descriptor, authority, current = self._load(tenant_id, agent_id)
        if current.state in _TERMINAL_STATES:
            return current
        return self._append(
            tenant_id,
            descriptor,
            authority,
            current,
            state=AgentLifecycleState.CANCELLED,
            active_task_ids=(),
            reason=reason,
        )

    def complete(self, tenant_id: str, agent_id: str) -> AgentCheckpoint:
        descriptor, authority, current = self._load(tenant_id, agent_id)
        if current.state is not AgentLifecycleState.RUNNING:
            raise AgentRuntimeDenied("only a running agent may complete")
        if current.active_task_ids:
            raise AgentRuntimeDenied(
                "agent cannot complete while tasks are active"
            )
        return self._append(
            tenant_id,
            descriptor,
            authority,
            current,
            state=AgentLifecycleState.COMPLETED,
            reason="completed",
        )

    def fail(
        self,
        tenant_id: str,
        agent_id: str,
        *,
        reason: str = "failed",
    ) -> AgentCheckpoint:
        descriptor, authority, current = self._load(tenant_id, agent_id)
        if current.state in _TERMINAL_STATES:
            return current
        return self._append(
            tenant_id,
            descriptor,
            authority,
            current,
            state=AgentLifecycleState.FAILED,
            active_task_ids=(),
            reason=reason,
        )

    def acquire_task(
        self,
        tenant_id: str,
        agent_id: str,
        task_id: str,
    ) -> AgentCheckpoint:
        descriptor, authority, current = self._load(tenant_id, agent_id)
        task = _token(task_id, "task_id")
        if current.state is not AgentLifecycleState.RUNNING:
            raise AgentRuntimeDenied("agent must be running to acquire tasks")
        if task in current.active_task_ids:
            return current
        limit = min(
            descriptor.budget.max_parallel_tasks,
            authority.budget.max_parallel_tasks,
        )
        if len(current.active_task_ids) >= limit:
            raise AgentRuntimeDenied("agent parallel-task budget exhausted")
        return self._append(
            tenant_id,
            descriptor,
            authority,
            current,
            active_task_ids=(*current.active_task_ids, task),
            reason="task-acquired",
            require_live_authority=True,
        )

    def release_task(
        self,
        tenant_id: str,
        agent_id: str,
        task_id: str,
    ) -> AgentCheckpoint:
        descriptor, authority, current = self._load(tenant_id, agent_id)
        task = _token(task_id, "task_id")
        if task not in current.active_task_ids:
            raise AgentRuntimeConflict("agent does not own active task")
        return self._append(
            tenant_id,
            descriptor,
            authority,
            current,
            active_task_ids=tuple(
                item for item in current.active_task_ids if item != task
            ),
            reason="task-released",
        )

    def record_usage(
        self,
        tenant_id: str,
        agent_id: str,
        *,
        steps: int = 0,
        tokens: int = 0,
        cost_units: float = 0.0,
        wall_time_s: float = 0.0,
    ) -> AgentCheckpoint:
        descriptor, authority, current = self._load(tenant_id, agent_id)
        if current.state is not AgentLifecycleState.RUNNING:
            raise AgentRuntimeDenied("agent must be running to record usage")
        usage = current.usage.add(
            steps=steps,
            tokens=tokens,
            cost_units=cost_units,
            wall_time_s=wall_time_s,
        )
        if not usage.within(descriptor.budget):
            raise AgentRuntimeDenied("descriptor resource budget exhausted")
        if not usage.within(authority.budget):
            raise AgentRuntimeDenied("delegated resource budget exhausted")
        return self._append(
            tenant_id,
            descriptor,
            authority,
            current,
            usage=usage,
            reason="usage-recorded",
        )


__all__ = [
    "AGENT_RUNTIME_SCHEMA_VERSION",
    "AgentCheckpoint",
    "AgentDescriptor",
    "AgentLifecycleState",
    "AgentResourceUsage",
    "AgentRuntimeConflict",
    "AgentRuntimeDenied",
    "AgentRuntimeError",
    "DurableAgentSupervisor",
    "SQLiteAgentRuntimeStore",
]
