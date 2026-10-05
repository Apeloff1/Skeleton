"""Serializable skill identity and promotion state."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List
import json

@dataclass
class SkillManifest:
    name: str
    version: str = "0.1.0"
    capabilities: List[str] = field(default_factory=list)
    preconditions: List[str] = field(default_factory=list)
    invariants: List[str] = field(default_factory=list)
    evaluation: List[str] = field(default_factory=list)
    provenance: str = "local"

    def to_dict(self) -> Dict[str, Any]: return asdict(self)
    def dumps(self) -> str: return json.dumps(self.to_dict(), indent=2, sort_keys=True)
    @classmethod
    def loads(cls, text: str) -> "SkillManifest": return cls(**json.loads(text))

@dataclass
class SkillState:
    status: str = "draft"
    attempts: int = 0
    successes: int = 0
    regressions: int = 0
    last_trace: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        return self.successes / self.attempts if self.attempts else 0.0

    def record(self, success: bool, trace: str = "") -> None:
        self.attempts += 1
        if success: self.successes += 1
        else: self.regressions += 1
        self.last_trace = trace

    def to_dict(self) -> Dict[str, Any]: return asdict(self)
