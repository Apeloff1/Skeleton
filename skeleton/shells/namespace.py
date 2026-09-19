"""Namespaced shell control-plane boundaries for multi-tenant callers."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
import threading
from types import MappingProxyType
from typing import Mapping

_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$")


@dataclass(frozen=True)
class ShellNamespace:
    name: str
    principals: frozenset[str] = frozenset()
    command_prefixes: frozenset[str] = frozenset()
    metadata: Mapping[str, str] = field(default_factory=dict)
    enabled: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not _NAME.fullmatch(self.name):
            raise ValueError("invalid namespace name")
        principals = frozenset(self.principals)
        prefixes = frozenset(self.command_prefixes)
        if any(not value or len(value) > 256 for value in principals):
            raise ValueError("invalid namespace principal")
        if any(not value or len(value) > 128 for value in prefixes):
            raise ValueError("invalid command prefix")
        metadata = dict(self.metadata)
        object.__setattr__(self, "principals", principals)
        object.__setattr__(self, "command_prefixes", prefixes)
        object.__setattr__(self, "metadata", MappingProxyType(metadata))

    def allows_principal(self, principal: str) -> bool:
        return self.enabled and (not self.principals or principal in self.principals)

    def allows_command(self, command: str) -> bool:
        if not self.enabled:
            return False
        return not self.command_prefixes or any(command.startswith(prefix) for prefix in self.command_prefixes)


class NamespaceRegistry:
    def __init__(self, *, max_namespaces: int = 1000) -> None:
        if max_namespaces <= 0:
            raise ValueError("max_namespaces must be positive")
        self.max_namespaces = max_namespaces
        self._items: dict[str, ShellNamespace] = {}
        self._lock = threading.RLock()

    def set(self, namespace: ShellNamespace) -> None:
        with self._lock:
            if namespace.name not in self._items and len(self._items) >= self.max_namespaces:
                raise RuntimeError("namespace capacity exhausted")
            self._items[namespace.name] = namespace

    def get(self, name: str) -> ShellNamespace:
        with self._lock:
            return self._items[name]

    def authorize(self, name: str, *, principal: str, command: str) -> None:
        namespace = self.get(name)
        if not namespace.allows_principal(principal):
            raise PermissionError("principal is outside shell namespace")
        if not namespace.allows_command(command):
            raise PermissionError("command is outside shell namespace")

    def remove(self, name: str) -> bool:
        with self._lock:
            return self._items.pop(name, None) is not None

    def snapshot(self) -> tuple[ShellNamespace, ...]:
        with self._lock:
            return tuple(self._items[key] for key in sorted(self._items))
