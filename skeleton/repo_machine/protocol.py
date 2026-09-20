"""Typed, non-executing protocol for machine repository queries.

The protocol intentionally exposes analysis only. It does not accept shell
commands, executable names, workflow permissions, tokens, or arbitrary Python
entrypoints. Mutation remains outside this package.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Mapping

from .config import MachineConfig
from .context import context_for_intent
from .coordinator import build_coordinator_snapshot
from .debt import debt_register
from .hotspots import structural_hotspots
from .model import RepositoryModel
from .reorganize import propose_reorganization
from .retrieval import RepositoryRetrievalIndex
from .session import build_machine_session

_ALLOWED_OPERATIONS = {
    "overview",
    "search",
    "hotspots",
    "debt",
    "reorganization",
    "session",
    "context",
}
_ALLOWED_CONTEXT_INTENTS = {
    "overview",
    "repair",
    "architecture",
    "testing",
    "security",
    "documentation",
    "performance",
}
MAX_QUERY_CHARS = 1000
MAX_RESPONSE_BYTES = 96_000


@dataclass(frozen=True, slots=True)
class MachineRequest:
    operation: str
    query: str = ""
    intent: str = "overview"
    limit: int = 40

    def __post_init__(self) -> None:
        if self.operation not in _ALLOWED_OPERATIONS:
            raise ValueError("unsupported machine operation")
        if not isinstance(self.query, str) or len(self.query) > MAX_QUERY_CHARS:
            raise ValueError("query exceeds machine protocol limit")
        if self.intent not in _ALLOWED_CONTEXT_INTENTS:
            raise ValueError("unsupported context intent")
        if isinstance(self.limit, bool) or not isinstance(self.limit, int) or not 1 <= self.limit <= 200:
            raise ValueError("limit must be in [1,200]")
        if self.operation == "search" and not self.query.strip():
            raise ValueError("search operation requires query")

    def as_dict(self) -> dict[str, object]:
        return {
            "operation": self.operation,
            "query": self.query,
            "intent": self.intent,
            "limit": self.limit,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> "MachineRequest":
        return cls(
            operation=str(value.get("operation", "")),
            query=str(value.get("query", "")),
            intent=str(value.get("intent", "overview")),
            limit=int(value.get("limit", 40)),
        )


@dataclass(frozen=True, slots=True)
class MachineResponse:
    operation: str
    repository_fingerprint: str
    payload: dict[str, object]
    truncated: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "operation": self.operation,
            "repository_fingerprint": self.repository_fingerprint,
            "payload": self.payload,
            "truncated": self.truncated,
        }


def _bounded(response: MachineResponse) -> MachineResponse:
    raw = json.dumps(response.as_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(raw) <= MAX_RESPONSE_BYTES:
        return response
    payload = dict(response.payload)
    for key in ("hits", "hotspots", "debt", "proposals", "work_candidates"):
        value = payload.get(key)
        if isinstance(value, list):
            payload[key] = value[:12]
    coordinator = payload.get("coordinator")
    if isinstance(coordinator, dict):
        payload["coordinator"] = {
            "repository_fingerprint": coordinator.get("repository_fingerprint"),
            "health": coordinator.get("health", {}),
            "steward": coordinator.get("steward", {}),
            "queue_ready": coordinator.get("queue_ready", [])[:3],
        }
    return MachineResponse(
        operation=response.operation,
        repository_fingerprint=response.repository_fingerprint,
        payload=payload,
        truncated=True,
    )


def handle_request(
    model: RepositoryModel,
    config: MachineConfig,
    request: MachineRequest,
) -> MachineResponse:
    if request.operation == "overview":
        payload = build_coordinator_snapshot(model, config).as_dict()
    elif request.operation == "search":
        payload = {
            "query": request.query,
            "hits": [
                item.as_dict()
                for item in RepositoryRetrievalIndex(model).search(
                    request.query,
                    limit=request.limit,
                )
            ],
        }
    elif request.operation == "hotspots":
        payload = {
            "hotspots": [
                item.as_dict()
                for item in structural_hotspots(model, limit=request.limit)
            ]
        }
    elif request.operation == "debt":
        payload = {
            "debt": [
                item.as_dict()
                for item in debt_register(model, limit=request.limit)
            ]
        }
    elif request.operation == "reorganization":
        payload = {
            "proposals": [
                item.as_dict()
                for item in propose_reorganization(
                    model,
                    config,
                    limit=request.limit,
                )
            ]
        }
    elif request.operation == "session":
        payload = build_machine_session(
            model,
            config,
            now=1,
        ).as_dict()
    elif request.operation == "context":
        payload = context_for_intent(model, request.intent)
    else:
        raise AssertionError("unreachable operation")
    return _bounded(MachineResponse(
        operation=request.operation,
        repository_fingerprint=model.fingerprint,
        payload=payload,
    ))
