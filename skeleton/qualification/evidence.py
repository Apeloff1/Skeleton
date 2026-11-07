from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import SchemaError

SHA_RE = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class Evidence:
    case_id: str
    head_sha: str
    source: str  # "ci", "device", "manual"
    data: dict = field(default_factory=dict)
    digest: str = ""

    def bound_to(self, head_sha: str) -> bool:
        return self.head_sha == head_sha


def canonical_digest(data: Any) -> str:
    blob = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()


def parse_evidence(doc: Any, where: str = "<evidence>") -> Evidence:
    if not isinstance(doc, dict):
        raise SchemaError(where, "evidence must be an object")
    for key in ("case_id", "head_sha", "source", "data"):
        if key not in doc:
            raise SchemaError(where, f"missing required field '{key}'")
    if not SHA_RE.match(str(doc["head_sha"])):
        raise SchemaError(where, "head_sha must be a full 40-char lowercase SHA")
    if doc["source"] not in ("ci", "device", "manual"):
        raise SchemaError(where, "source must be ci, device or manual")
    if not isinstance(doc["data"], dict):
        raise SchemaError(where, "data must be an object")
    digest = canonical_digest(doc["data"])
    claimed = doc.get("digest")
    if claimed is not None and claimed != digest:
        raise SchemaError(where, "digest does not match data (tampered or stale)")
    return Evidence(doc["case_id"], doc["head_sha"], doc["source"], doc["data"], digest)


def load_evidence(directory: str | Path) -> dict[str, Evidence]:
    out: dict[str, Evidence] = {}
    d = Path(directory)
    if not d.exists():
        return out
    for p in sorted(d.glob("*.json")):
        ev = parse_evidence(json.loads(p.read_text(encoding="utf-8")), str(p))
        if ev.case_id in out:
            raise SchemaError(str(p), f"duplicate evidence for {ev.case_id}")
        out[ev.case_id] = ev
    return out
