"""Scoped executable studio commands for the existing Jeeves tool registry.

The host injects current application owners and exact-command authorization.
Tool registration grants no source, account, controller, compiler or consent
rights. Commands enqueue governed work rather than creating another scheduler.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

SCHEMA = "skeleton.game.studio_command.v1"
MAX_PAYLOAD = 256 * 1024
MAX_RESULT = 512 * 1024
READ_OPERATIONS = (
    "catalog",
    "project.inspect",
    "source.inspect",
    "console.inspect",
    "console.handoff",
    "successor.inspect",
    "job.inspect",
    "play.inspect",
    "campaign.inspect",
    "campaign.rounds",
    "lessons.search",
)
WRITE_OPERATIONS = (
    "console.edit",
    "world.edit",
    "simulate",
    "build",
    "train",
    "successor.synthesize",
    "successor.compare",
    "desktop.build",
    "play.start",
    "play.input",
    "play.control",
    "campaign.create",
    "campaign.pulse",
    "campaign.pause",
    "campaign.resume",
    "campaign.cancel",
)
OPERATIONS = frozenset((*READ_OPERATIONS, *WRITE_OPERATIONS))


def _canonical(value: Any, maximum: int) -> bytes:
    try:
        raw = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode()
    except (TypeError, ValueError, RecursionError) as exc:
        raise ValueError("Studio commands and results require finite bounded JSON") from exc
    if len(raw) > maximum:
        raise ValueError("Studio command or result exceeds its byte budget")
    return raw


@dataclass(frozen=True, slots=True)
class StudioCommand:
    operation: str
    project_id: str
    payload: Mapping[str, Any]

    def __post_init__(self):
        if self.operation not in OPERATIONS:
            raise ValueError("Unknown studio operation")
        if (
            not isinstance(self.project_id, str)
            or not 1 <= len(self.project_id) <= 128
            or self.project_id != self.project_id.strip()
        ):
            raise ValueError("Studio command requires an exact bounded project identity")
        if not isinstance(self.payload, Mapping) or len(self.payload) > 64:
            raise ValueError("Studio payload must be a bounded object")
        frozen = json.loads(_canonical(dict(self.payload), MAX_PAYLOAD))
        object.__setattr__(self, "payload", MappingProxyType(frozen))

    @property
    def mutates(self) -> bool:
        return self.operation in WRITE_OPERATIONS

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA,
            "operation": self.operation,
            "project_id": self.project_id,
            "payload": dict(self.payload),
        }

    @property
    def digest(self) -> str:
        return hashlib.sha256(_canonical(self.as_dict(), MAX_PAYLOAD + 1024)).hexdigest()


def studio_command_catalog() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA,
        "read_operations": list(READ_OPERATIONS),
        "write_operations": list(WRITE_OPERATIONS),
        "payload_bytes": MAX_PAYLOAD,
        "authority": "Current host-scoped owners plus tool grant; registration never grants execution",
        "learning": "Actual campaign rounds and governed learner jobs retain source/code/policy-bound evidence; queued jobs are not completed work",
    }


def register_studio_tools(
    registry, *, handlers: Mapping[str, Callable], authorize: Callable
) -> tuple[str, ...]:
    from .agent.tools import ArgumentRule, ToolDenied, ToolRegistry, ToolSpec
    from .agent.types import RiskTier

    if not isinstance(registry, ToolRegistry) or not isinstance(handlers, Mapping) or not handlers:
        raise TypeError("Studio tools require a host registry and nonempty owner handlers")
    if not callable(authorize) or any(
        name not in OPERATIONS or not callable(handler) for name, handler in handlers.items()
    ):
        raise TypeError("Studio operations and exact-command authorizer must be trusted host callbacks")
    trusted = dict(handlers)
    names = []
    for writable, tool_name in ((False, "studio_inspect"), (True, "studio_execute")):
        enabled = tuple(sorted(name for name in trusted if (name in WRITE_OPERATIONS) is writable))
        if not enabled:
            continue

        def perform(arguments, context, *, allowed=enabled):
            command = StudioCommand(arguments["operation"], arguments["project_id"], arguments["payload"])
            if command.operation not in allowed or authorize(command, context) is not True:
                raise ToolDenied("Current host did not authorize this exact studio command")
            result = trusted[command.operation](command, context)
            safe = json.loads(_canonical(result, MAX_RESULT))
            return {
                "schema_version": "skeleton.game.studio_tool_receipt.v1",
                "command_digest": command.digest,
                "operation": command.operation,
                "project_id": command.project_id,
                "result_digest": hashlib.sha256(_canonical(safe, MAX_RESULT)).hexdigest(),
                "result": safe,
            }

        spec = ToolSpec(
            name=tool_name,
            description=(
                "Inspect current scoped studio evidence"
                if not writable
                else "Execute a scoped editor, build, play or learning command through existing application owners; a returned queued job is not completed work"
            ),
            risk=RiskTier.MUTATING if writable else RiskTier.READ_ONLY,
            arguments=(
                ArgumentRule("operation", "string", choices=enabled),
                ArgumentRule("project_id", "string", max_length=128),
                ArgumentRule("payload", "object", max_length=64),
            ),
            idempotent=not writable,
            cache_ttl_seconds=None,
            timeout_seconds=25,
            produces_evidence=True,
        )
        registry.register(spec, perform)
        names.append(tool_name)
    return tuple(names)
