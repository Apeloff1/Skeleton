"""Fail-closed retrieval scope contract.

A RetrievalScope is an immutable set of authorization/data-boundary labels.
Scoped retrieval may only dispatch to planes that expose query_scoped, so a
caller cannot accidentally apply authorization after ranking.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Tuple


class ScopedRetrievalError(RuntimeError):
    """Scoped retrieval cannot be executed without pre-ranking enforcement."""


@dataclass(frozen=True, slots=True)
class RetrievalScope:
    values: Tuple[Tuple[str, str], ...]

    def __post_init__(self) -> None:
        keys = []
        for key, value in self.values:
            if not isinstance(key, str) or not key.strip():
                raise ValueError("scope keys must be non-empty strings")
            if not isinstance(value, str) or not value.strip():
                raise ValueError("scope values must be non-empty strings")
            keys.append(key)
        if len(keys) != len(set(keys)):
            raise ValueError("scope keys must be unique")
        if not self.values:
            raise ValueError("scope must contain at least one boundary")

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "RetrievalScope":
        if not isinstance(raw, Mapping):
            raise TypeError("scope must be a mapping")
        rows = []
        for key, value in raw.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise ValueError("scope keys and values must be strings")
            rows.append((key.strip(), value.strip()))
        return cls(tuple(sorted(rows)))

    def to_dict(self) -> Dict[str, str]:
        return dict(self.values)

    @property
    def digest(self) -> str:
        encoded = json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.blake2b(encoded, digest_size=16).hexdigest()
