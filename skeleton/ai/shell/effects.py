"""Declarative effect contracts for model-visible shell commands."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import threading
from types import MappingProxyType
from typing import Mapping


class EffectKind(str, Enum):
    READ_FILESYSTEM = "read_filesystem"
    WRITE_FILESYSTEM = "write_filesystem"
    DELETE_FILESYSTEM = "delete_filesystem"
    NETWORK = "network"
    PROCESS_CONTROL = "process_control"
    PACKAGE_CHANGE = "package_change"
    VCS_READ = "vcs_read"
    VCS_WRITE = "vcs_write"
    SECRET_ACCESS = "secret_access"
    PRIVILEGED = "privileged"
    DEPLOYMENT = "deployment"
    EXTERNAL_SIDE_EFFECT = "external_side_effect"


@dataclass(frozen=True)
class EffectContract:
    command: str
    effects: frozenset[EffectKind] = frozenset()
    idempotent: bool = False
    reversible: bool = False
    compensation_command: str = ""
    human_approval_recommended: bool = False
    tags: frozenset[str] = frozenset()
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.command or len(self.command) > 128:
            raise ValueError("invalid effect command")
        effects = frozenset(EffectKind(item) for item in self.effects)
        if self.compensation_command and not self.reversible:
            raise ValueError("compensation command requires reversible contract")
        if len(self.compensation_command) > 128:
            raise ValueError("compensation command too long")
        tags = frozenset(self.tags)
        if len(tags) > 64 or any(not item or len(item) > 128 for item in tags):
            raise ValueError("invalid effect tags")
        metadata = dict(self.metadata)
        if len(metadata) > 64:
            raise ValueError("too many effect metadata fields")
        if any(
            not isinstance(key, str)
            or not isinstance(value, str)
            or len(key) > 128
            or len(value) > 512
            for key, value in metadata.items()
        ):
            raise ValueError("invalid effect metadata")
        object.__setattr__(self, "effects", effects)
        object.__setattr__(self, "tags", tags)
        object.__setattr__(self, "metadata", MappingProxyType(metadata))

    @property
    def destructive(self) -> bool:
        return bool(
            self.effects
            & {
                EffectKind.DELETE_FILESYSTEM,
                EffectKind.PACKAGE_CHANGE,
                EffectKind.VCS_WRITE,
                EffectKind.DEPLOYMENT,
                EffectKind.PRIVILEGED,
            }
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "command": self.command,
            "effects": sorted(item.value for item in self.effects),
            "idempotent": self.idempotent,
            "reversible": self.reversible,
            "compensation_command": self.compensation_command,
            "human_approval_recommended": self.human_approval_recommended,
            "tags": sorted(self.tags),
            "metadata": dict(self.metadata),
        }


class EffectRegistry:
    def __init__(self, contracts: tuple[EffectContract, ...] = (), *, max_commands: int = 4096) -> None:
        if max_commands <= 0:
            raise ValueError("max_commands must be positive")
        self.max_commands = max_commands
        self._items: dict[str, EffectContract] = {}
        self._lock = threading.RLock()
        for contract in contracts:
            self.register(contract)

    def register(self, contract: EffectContract, *, replace: bool = False) -> None:
        with self._lock:
            if contract.command in self._items and not replace:
                raise ValueError("effect contract already exists")
            if contract.command not in self._items and len(self._items) >= self.max_commands:
                raise RuntimeError("effect registry capacity exhausted")
            self._items[contract.command] = contract

    def get(self, command: str) -> EffectContract:
        with self._lock:
            return self._items[command]

    def inspect(self, command: str) -> EffectContract | None:
        with self._lock:
            return self._items.get(command)

    def remove(self, command: str) -> bool:
        with self._lock:
            return self._items.pop(command, None) is not None

    def snapshot(self) -> tuple[EffectContract, ...]:
        with self._lock:
            return tuple(self._items[key] for key in sorted(self._items))

    @property
    def digest(self) -> str:
        payload = [item.to_dict() for item in self.snapshot()]
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(raw).hexdigest()
