"""Versioned evaluation dataset primitives for AI shell planning."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from types import MappingProxyType
from typing import Mapping

from skeleton.shells.ai.effects import EffectKind
from skeleton.shells.ai.types import AIIntent


@dataclass(frozen=True)
class AIEvalCase:
    case_id: str
    intent: AIIntent
    required_commands: frozenset[str] = frozenset()
    forbidden_commands: frozenset[str] = frozenset()
    required_effects: frozenset[EffectKind] = frozenset()
    forbidden_effects: frozenset[EffectKind] = frozenset()
    max_actions: int = 32
    must_require_approval: bool | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.case_id or len(self.case_id) > 160:
            raise ValueError("invalid eval case_id")
        if self.max_actions <= 0 or self.max_actions > 1024:
            raise ValueError("eval max_actions out of range")
        required_commands = frozenset(self.required_commands)
        forbidden_commands = frozenset(self.forbidden_commands)
        if required_commands & forbidden_commands:
            raise ValueError("eval command cannot be both required and forbidden")
        required_effects = frozenset(EffectKind(item) for item in self.required_effects)
        forbidden_effects = frozenset(EffectKind(item) for item in self.forbidden_effects)
        if required_effects & forbidden_effects:
            raise ValueError("eval effect cannot be both required and forbidden")
        metadata = dict(self.metadata)
        if len(metadata) > 64:
            raise ValueError("too many eval metadata fields")
        object.__setattr__(self, "required_commands", required_commands)
        object.__setattr__(self, "forbidden_commands", forbidden_commands)
        object.__setattr__(self, "required_effects", required_effects)
        object.__setattr__(self, "forbidden_effects", forbidden_effects)
        object.__setattr__(self, "metadata", MappingProxyType(metadata))

    def to_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "intent": self.intent.to_dict(),
            "required_commands": sorted(self.required_commands),
            "forbidden_commands": sorted(self.forbidden_commands),
            "required_effects": sorted(item.value for item in self.required_effects),
            "forbidden_effects": sorted(item.value for item in self.forbidden_effects),
            "max_actions": self.max_actions,
            "must_require_approval": self.must_require_approval,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class AIEvalDataset:
    dataset_id: str
    version: int
    cases: tuple[AIEvalCase, ...]
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.dataset_id or len(self.dataset_id) > 160:
            raise ValueError("invalid eval dataset_id")
        if self.version <= 0:
            raise ValueError("eval dataset version must be positive")
        cases = tuple(self.cases)
        if not cases:
            raise ValueError("eval dataset requires cases")
        ids = [item.case_id for item in cases]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate eval case_id")
        metadata = dict(self.metadata)
        object.__setattr__(self, "cases", cases)
        object.__setattr__(self, "metadata", MappingProxyType(metadata))

    def to_dict(self) -> dict[str, object]:
        return {
            "dataset_id": self.dataset_id,
            "version": self.version,
            "cases": [item.to_dict() for item in self.cases],
            "metadata": dict(self.metadata),
        }

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()
