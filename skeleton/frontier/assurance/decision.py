"""Explicit immutable decision records for auditable control flow."""
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType


@dataclass(frozen=True)
class Decision:
    action: str
    allowed: bool
    reason: str
    evidence: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for value in (self.action, self.reason):
            if type(value) is not str or not value.strip() or len(value) > 4096:
                raise ValueError("invalid decision text")
        if type(self.allowed) is not bool:
            raise ValueError("allowed must be a boolean")
        if type(self.evidence) not in (dict, MappingProxyType) or len(self.evidence) > 4096:
            raise ValueError("invalid decision evidence")
        evidence = dict(self.evidence)
        if any(type(k) is not str or not k.strip() or len(k) > 1024
               or type(v) is not str or len(v) > 4096 for k, v in evidence.items()):
            raise ValueError("invalid evidence entry")
        object.__setattr__(self, "evidence", MappingProxyType(evidence))
