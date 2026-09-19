"""Provenance labels for model context entering the AI shell planner."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
from types import MappingProxyType
from typing import Mapping


class ContextTrust(str, Enum):
    SYSTEM = "system"
    TRUSTED = "trusted"
    USER = "user"
    UNTRUSTED = "untrusted"


class ContextSensitivity(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    SECRET = "secret"


class ContextKind(str, Enum):
    GOAL = "goal"
    POLICY = "policy"
    OBSERVATION = "observation"
    REPOSITORY = "repository"
    USER_DATA = "user_data"
    TOOL_DATA = "tool_data"
    SYSTEM_STATE = "system_state"


@dataclass(frozen=True)
class ContextItem:
    item_id: str
    kind: ContextKind
    trust: ContextTrust
    sensitivity: ContextSensitivity
    content: str
    source: str
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.item_id or len(self.item_id) > 160:
            raise ValueError("invalid context item_id")
        if len(self.content) > 65536:
            raise ValueError("context item too large")
        if not self.source or len(self.source) > 512:
            raise ValueError("invalid context source")
        metadata = dict(self.metadata)
        if len(metadata) > 64:
            raise ValueError("too many context metadata fields")
        object.__setattr__(self, "kind", ContextKind(self.kind))
        object.__setattr__(self, "trust", ContextTrust(self.trust))
        object.__setattr__(self, "sensitivity", ContextSensitivity(self.sensitivity))
        object.__setattr__(self, "metadata", MappingProxyType(metadata))

    def to_dict(self, *, include_content: bool = True) -> dict[str, object]:
        data = {
            "item_id": self.item_id,
            "kind": self.kind.value,
            "trust": self.trust.value,
            "sensitivity": self.sensitivity.value,
            "source": self.source,
            "metadata": dict(self.metadata),
            "content_digest": hashlib.sha256(self.content.encode()).hexdigest(),
        }
        if include_content:
            data["content"] = self.content
        return data


@dataclass(frozen=True)
class ContextBundle:
    items: tuple[ContextItem, ...]
    max_total_bytes: int = 131072

    def __post_init__(self) -> None:
        items = tuple(self.items)
        ids = [item.item_id for item in items]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate context item_id")
        if self.max_total_bytes <= 0:
            raise ValueError("max_total_bytes must be positive")
        total = sum(len(item.content.encode()) for item in items)
        if total > self.max_total_bytes:
            raise ValueError("context bundle exceeds byte budget")
        object.__setattr__(self, "items", items)

    @property
    def digest(self) -> str:
        raw = json.dumps(
            [item.to_dict(include_content=False) for item in self.items],
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    @property
    def secret_items(self) -> tuple[ContextItem, ...]:
        return tuple(
            item
            for item in self.items
            if item.sensitivity is ContextSensitivity.SECRET
        )

    @property
    def untrusted_items(self) -> tuple[ContextItem, ...]:
        return tuple(
            item
            for item in self.items
            if item.trust is ContextTrust.UNTRUSTED
        )

    def model_safe(self) -> "ContextBundle":
        safe = tuple(
            item
            for item in self.items
            if item.sensitivity is not ContextSensitivity.SECRET
        )
        return ContextBundle(safe, self.max_total_bytes)

    def to_model_payload(self) -> tuple[dict[str, object], ...]:
        if self.secret_items:
            raise ValueError("secret context must be removed before model exposure")
        return tuple(
            {
                "item_id": item.item_id,
                "kind": item.kind.value,
                "trust": item.trust.value,
                "sensitivity": item.sensitivity.value,
                "source": item.source,
                "content": item.content,
            }
            for item in self.items
        )
