from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import SchemaError

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
CASE_RE = re.compile(r"^GFM-[A-Z]{1,8}-[0-9]{2,3}$")
MAX_EVIDENCE_BYTES = 262144
MAX_EVIDENCE_FILES = 256


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
    try:
        blob = json.dumps(data, sort_keys=True, separators=(",", ":"),
                          allow_nan=False, ensure_ascii=True).encode("ascii")
    except (TypeError, ValueError, RecursionError, OverflowError) as exc:
        raise ValueError("noncanonical qualification evidence") from exc
    if len(blob) > MAX_EVIDENCE_BYTES:
        raise ValueError("qualification evidence byte budget exceeded")
    return hashlib.sha256(blob).hexdigest()


def parse_evidence(doc: Any, where: str = "<evidence>") -> Evidence:
    if not isinstance(doc, dict):
        raise SchemaError(where, "evidence must be an object")
    required = {"case_id", "head_sha", "source", "data"}
    missing = required - set(doc)
    if missing:
        raise SchemaError(where, f"missing evidence fields: {', '.join(sorted(missing))}")
    if set(doc) - (required | {"digest"}):
        raise SchemaError(where, "unknown evidence fields")
    if type(doc["case_id"]) is not str or CASE_RE.fullmatch(doc["case_id"]) is None:
        raise SchemaError(where, "invalid qualification case identifier")
    if type(doc["head_sha"]) is not str or SHA_RE.fullmatch(doc["head_sha"]) is None:
        raise SchemaError(where, "head_sha must be a full 40-char lowercase SHA")
    if type(doc["source"]) is not str or doc["source"] not in ("ci", "device", "manual"):
        raise SchemaError(where, "source must be ci, device or manual")
    if type(doc["data"]) is not dict:
        raise SchemaError(where, "data must be an object")
    try:
        digest = canonical_digest(doc["data"])
    except ValueError as exc:
        raise SchemaError(where, "invalid bounded evidence data") from exc
    claimed = doc.get("digest")
    if claimed is not None and claimed != digest:
        raise SchemaError(where, "digest does not match data (tampered or stale)")
    return Evidence(doc["case_id"], doc["head_sha"], doc["source"], doc["data"], digest)


def load_evidence(directory: str | Path) -> dict[str, Evidence]:
    """A stable, owner-controlled and finite source snapshot; never device proof."""
    from .secure_fs import decode, read_inventory
    result: dict[str, Evidence] = {}
    for where, raw in read_inventory(
        directory, max_files=MAX_EVIDENCE_FILES, max_bytes=MAX_EVIDENCE_BYTES,
        max_total=8 * 1024 * 1024,
    ):
        ev = parse_evidence(decode(raw, str(where)), str(where))
        if ev.case_id in result:
            raise SchemaError(str(where), f"duplicate evidence for {ev.case_id}")
        result[ev.case_id] = ev
    return result
