"""Principal-bound replay protection for MCP tool-call requests."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import time
from typing import Callable

from skeleton.shells.ai.distributed_idempotency import DistributedAIIdempotencyRegistry
from skeleton.shells.ai.idempotency import AIIdempotencyConflict
from skeleton.shells.ai.mcp import MCPRequestEnvelope


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
    """Bind one request ID to one principal and one canonical request payload.

    Transport authentication establishes principal identity. This guard does not
    authenticate a caller; it prevents a successfully authenticated request ID
    from being replayed or reused with different content across workers.
    """

    def __init__(
        self,
        registry: DistributedAIIdempotencyRegistry,
        *,
        default_ttl_seconds: float = 300.0,
        max_ttl_seconds: float = 3600.0,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if default_ttl_seconds <= 0 or max_ttl_seconds <= 0:
            raise ValueError("MCP replay TTLs must be positive")
        if default_ttl_seconds > max_ttl_seconds:
            raise ValueError("MCP default replay TTL exceeds maximum")
        self.registry = registry
        self.default_ttl_seconds = default_ttl_seconds
        self.max_ttl_seconds = max_ttl_seconds
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
    def _proposal_binding(request_digest: str) -> str:
        # DistributedAIIdempotencyRegistry binds two SHA-256 values. For MCP
        # admission there is no AI proposal yet, so bind a domain-separated
        # second digest rather than reusing raw request_digest twice.
        return hashlib.sha256(
            b"mcp-request-admission:" + request_digest.encode()
        ).hexdigest()

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
        key = f"{principal}:{request.request_id}"
        now = self._clock()
        try:
            record = self.registry.register(
                key,
                request_digest=digest,
                proposal_fingerprint=self._proposal_binding(digest),
                ttl_seconds=ttl,
            )
        except AIIdempotencyConflict as exc:
            raise MCPRequestReplay(
                "MCP request ID was reused with different principal-bound content"
            ) from exc
        return MCPRequestAdmission(
            request.request_id,
            principal,
            digest,
            now,
            record.expires_at,
        )

    def seen(
        self,
        request: MCPRequestEnvelope,
        *,
        principal: str,
    ) -> bool:
        key = f"{principal}:{request.request_id}"
        record = self.registry.get(key)
        if record is None:
            return False
        digest = self.request_digest(request, principal=principal)
        return record.request_digest == digest
