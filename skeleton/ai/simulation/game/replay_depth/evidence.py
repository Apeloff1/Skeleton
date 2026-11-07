"""Evidence bundle compare for deterministic replays."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Tuple


def compare_digests(expected: str, actual: str) -> Dict[str, Any]:
    ok = expected == actual and len(expected) == 64
    return {"ok": ok, "expected": expected, "actual": actual, "mismatch": None if ok else "digest"}


@dataclass(frozen=True)
class EvidenceBundle:
    schema: str
    schema_version: int
    digests: Tuple[str, ...]
    meta: Mapping[str, Any]

    def digest(self) -> str:
        body = json.dumps(
            {"schema": self.schema, "v": self.schema_version, "digests": list(self.digests), "meta": dict(self.meta)},
            sort_keys=True,
        )
        return hashlib.sha256(body.encode()).hexdigest()

    def verify_pair(self, other: "EvidenceBundle") -> Dict[str, Any]:
        return compare_digests(self.digest(), other.digest())
