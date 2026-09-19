"""Principal-bound single-use replay protection for MCP tool-call requests."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import time
from typing import Callable

from skeleton.shells.ai.distributed_state import DistributedStateConflict
from skeleton.shells.ai.mcp import MCPRequestEnvelope
from skeleton.shells.ai.store_protocol import VersionedStateBackend


@dataclass(frozen=True)
class MCPRequestAdmission:
    request_id: str
    principal: str
    request_digest: str
    admitted_at: float
    expires_at: float

    def __post_init__(self) -> None:
        if not self.request_id or len(self.request_id) > 160:
            raise ValueError("invalid MCP admission request_id")
        if not self.principal or len(self.principal) > 256:
            raise ValueError("invalid MCP admission principal")
        if len(self.request_digest) != 64:
            raise ValueError("MCP request digest must be SHA-256 hex")
        if self.expires_at <= self.admitted_at:
            raise ValueError("MCP request admission expiry invalid")

    def to_dict(self) -> dict[str, object]:
        return {
            "request_id": self.request_id,
            "principal": self.principal,
            "request_digest": self.request_digest,
            "admitted_at": self.admitted_at,
            "expires_at": self.expires_at,
        }


class MCPRequestReplay(RuntimeError):
    pass


class MCPReplayGuard:
    """Atomically admit one authenticated principal/request pair once.

    Authentication is intentionally outside this class. The caller supplies the
    already-authenticated principal. The replay store then binds request ID,
    principal, and canonical request bytes with put-if-absent so an identical
    retry is rejected as a replay rather than re-executed.
    """

    def __init__(
        self,
        backend: VersionedStateBackend,
        *,
        namespace: str = "shell-ai-mcp-replay",
        default_ttl_seconds: float = 300.0,
        max_ttl_seconds: float = 3600.0,
        max_retries: int = 4,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not namespace or len(namespace) > 128:
            raise ValueError("invalid MCP replay namespace")
        if default_ttl_seconds <= 0 or max_ttl_seconds <= 0:
            raise ValueError("MCP replay TTLs must be positive")
        if default_ttl_seconds > max_ttl_seconds:
            raise ValueError("MCP default replay TTL exceeds maximum")
        if max_retries <= 0:
            raise ValueError("MCP replay retry budget must be positive")
        self.backend = backend
        self.namespace = namespace
        self.default_ttl_seconds = default_ttl_seconds
        self.max_ttl_seconds = max_ttl_seconds
        self.max_retries = max_retries
        self._clock = clock

    @staticmethod
    def request_digest(
        request: MCPRequestEnvelope,
        *,
        principal: str,
    ) -> str:
        if not principal or len(principal) > 256:
            raise ValueError("invalid MCP principal")
        payload = {
            "principal": principal,
            "request": request.to_dict(),
        }
        raw = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    @staticmethod
    def _key(principal: str, request_id: str) -> str:
        raw = json.dumps(
            {"principal": principal, "request_id": request_id},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    def _current(self, principal: str, request_id: str):
        return self.backend.get(
            self.namespace,
            self._key(principal, request_id),
        )

    def admit(
        self,
        request: MCPRequestEnvelope,
        *,
        principal: str,
        ttl_seconds: float | None = None,
    ) -> MCPRequestAdmission:
        ttl = self.default_ttl_seconds if ttl_seconds is None else ttl_seconds
        if ttl <= 0 or ttl > self.max_ttl_seconds:
            raise ValueError("MCP replay TTL out of range")
        digest = self.request_digest(request, principal=principal)
        key = self._key(principal, request.request_id)
        for _ in range(self.max_retries):
            now = self._clock()
            existing = self.backend.get(self.namespace, key)
            if existing is not None:
                if not isinstance(existing.value, MCPRequestAdmission):
                    raise RuntimeError("MCP replay record type mismatch")
                if existing.value.expires_at > now:
                    raise MCPRequestReplay("MCP request already admitted")
                try:
                    self.backend.delete(
                        self.namespace,
                        key,
                        expected_revision=existing.revision,
                    )
                except DistributedStateConflict:
                    continue
            record = MCPRequestAdmission(
                request.request_id,
                principal,
                digest,
                now,
                now + ttl,
            )
            try:
                self.backend.put_if_absent(
                    self.namespace,
                    key,
                    record,
                )
                return record
            except DistributedStateConflict:
                continue
        raise MCPRequestReplay("MCP replay admission race did not converge")

    def seen(
        self,
        request: MCPRequestEnvelope,
        *,
        principal: str,
    ) -> bool:
        current = self._current(principal, request.request_id)
        if current is None:
            return False
        if not isinstance(current.value, MCPRequestAdmission):
            raise RuntimeError("MCP replay record type mismatch")
        if current.value.expires_at <= self._clock():
            return False
        digest = self.request_digest(request, principal=principal)
        return current.value.request_digest == digest

    def remaining_seconds(
        self,
        request: MCPRequestEnvelope,
        *,
        principal: str,
    ) -> float:
        current = self._current(principal, request.request_id)
        if current is None:
            return 0.0
        if not isinstance(current.value, MCPRequestAdmission):
            raise RuntimeError("MCP replay record type mismatch")
        return max(0.0, current.value.expires_at - self._clock())
