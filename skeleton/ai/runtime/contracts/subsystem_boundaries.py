"""Versioned internal boundaries between Skeleton subsystems.

These envelopes are the stable names kernel, agents, memory, GameForge, and
the API may exchange. They do not describe GameForge pipeline internals.
Transport, storage, and provider SDKs stay outside this module.
"""

from __future__ import annotations

from dataclasses import dataclass
import re


SUBSYSTEM_CONTRACT_VERSION = "1.0.0"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_NAME = re.compile(r"^[a-z][a-z0-9_]{1,63}$")


class SubsystemContractError(ValueError):
    """A subsystem boundary envelope is malformed."""


def _name(value: str, field: str) -> str:
    if not isinstance(value, str) or _NAME.fullmatch(value) is None:
        raise SubsystemContractError(f"{field} must be a lowercase identifier")
    return value


def _digest(value: str, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise SubsystemContractError(f"{field} must be lowercase sha256")
    return value


@dataclass(frozen=True)
class SubsystemContract:
    name: str
    version: str
    schema_id: str
    owner: str
    stability: str = "stable"

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _name(self.name, "name"))
        if self.version != SUBSYSTEM_CONTRACT_VERSION:
            raise SubsystemContractError("version is not the published subsystem contract version")
        if not isinstance(self.schema_id, str) or not self.schema_id.startswith("skeleton.subsystem."):
            raise SubsystemContractError("schema_id must live under skeleton.subsystem")
        if not isinstance(self.owner, str) or not self.owner.startswith("skeleton."):
            raise SubsystemContractError("owner must be a skeleton module path")
        if self.stability != "stable":
            raise SubsystemContractError("published subsystem contracts are stable")


KERNEL_CONTRACT = SubsystemContract(
    name="kernel",
    version=SUBSYSTEM_CONTRACT_VERSION,
    schema_id="skeleton.subsystem.kernel.v1",
    owner="skeleton.kernel",
)
AGENTS_CONTRACT = SubsystemContract(
    name="agents",
    version=SUBSYSTEM_CONTRACT_VERSION,
    schema_id="skeleton.subsystem.agents.v1",
    owner="skeleton.agents",
)
MEMORY_CONTRACT = SubsystemContract(
    name="memory",
    version=SUBSYSTEM_CONTRACT_VERSION,
    schema_id="skeleton.subsystem.memory.v1",
    owner="skeleton.memory",
)
GAMEFORGE_CONTRACT = SubsystemContract(
    name="gameforge",
    version=SUBSYSTEM_CONTRACT_VERSION,
    schema_id="skeleton.subsystem.gameforge.v1",
    owner="skeleton.api.routes",
)
API_CONTRACT = SubsystemContract(
    name="api",
    version=SUBSYSTEM_CONTRACT_VERSION,
    schema_id="skeleton.subsystem.api.v1",
    owner="skeleton.api",
)

SUBSYSTEM_CONTRACTS = {
    item.name: item
    for item in (
        KERNEL_CONTRACT,
        AGENTS_CONTRACT,
        MEMORY_CONTRACT,
        GAMEFORGE_CONTRACT,
        API_CONTRACT,
    )
}


@dataclass(frozen=True)
class KernelEventBoundary:
    event_type: str
    payload_digest: str
    schema_version: str = SUBSYSTEM_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SUBSYSTEM_CONTRACT_VERSION:
            raise SubsystemContractError("schema_version mismatch")
        object.__setattr__(self, "event_type", _name(self.event_type, "event_type"))
        object.__setattr__(self, "payload_digest", _digest(self.payload_digest, "payload_digest"))


@dataclass(frozen=True)
class AgentTaskBoundary:
    task_id: str
    capability: str
    payload_digest: str
    schema_version: str = SUBSYSTEM_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SUBSYSTEM_CONTRACT_VERSION:
            raise SubsystemContractError("schema_version mismatch")
        if not isinstance(self.task_id, str) or not self.task_id.strip() or self.task_id != self.task_id.strip():
            raise SubsystemContractError("task_id must be non-empty normalized text")
        object.__setattr__(self, "capability", _name(self.capability, "capability"))
        object.__setattr__(self, "payload_digest", _digest(self.payload_digest, "payload_digest"))


@dataclass(frozen=True)
class MemoryWriteBoundary:
    memory_id: str
    kind: str
    content_digest: str
    schema_version: str = SUBSYSTEM_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SUBSYSTEM_CONTRACT_VERSION:
            raise SubsystemContractError("schema_version mismatch")
        if not isinstance(self.memory_id, str) or not self.memory_id.strip():
            raise SubsystemContractError("memory_id must be non-empty")
        if self.kind not in {"episodic", "semantic", "procedural", "preference"}:
            raise SubsystemContractError("kind is not a canonical memory kind")
        object.__setattr__(self, "content_digest", _digest(self.content_digest, "content_digest"))


@dataclass(frozen=True)
class GameForgeCommandBoundary:
    """Facade only. ``run`` and ``intake`` match the mounted charter routes.

    Pipeline stages, prompts, and asset generation stay behind this digest.
    """

    command: str
    request_digest: str
    schema_version: str = SUBSYSTEM_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SUBSYSTEM_CONTRACT_VERSION:
            raise SubsystemContractError("schema_version mismatch")
        if self.command not in {"run", "intake"}:
            raise SubsystemContractError("command must be run or intake")
        object.__setattr__(self, "request_digest", _digest(self.request_digest, "request_digest"))


@dataclass(frozen=True)
class ApiErrorBoundary:
    code: str
    message: str
    schema_version: str = SUBSYSTEM_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SUBSYSTEM_CONTRACT_VERSION:
            raise SubsystemContractError("schema_version mismatch")
        if not isinstance(self.code, str) or not self.code or self.code != self.code.strip():
            raise SubsystemContractError("code must be non-empty normalized text")
        if not isinstance(self.message, str) or not self.message or self.message != self.message.strip():
            raise SubsystemContractError("message must be non-empty normalized text")

    def as_dict(self) -> dict[str, object]:
        return {
            "error": {
                "type": "SubsystemContractError",
                "code": self.code,
                "message": self.message,
                "context": {},
            }
        }


__all__ = [
    "API_CONTRACT",
    "AGENTS_CONTRACT",
    "ApiErrorBoundary",
    "AgentTaskBoundary",
    "GAMEFORGE_CONTRACT",
    "GameForgeCommandBoundary",
    "KERNEL_CONTRACT",
    "KernelEventBoundary",
    "MEMORY_CONTRACT",
    "MemoryWriteBoundary",
    "SUBSYSTEM_CONTRACTS",
    "SUBSYSTEM_CONTRACT_VERSION",
    "SubsystemContract",
    "SubsystemContractError",
]
