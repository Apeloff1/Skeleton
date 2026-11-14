"""skeleton/gameforge/manifest.py

Deterministic manifests: canonical JSON (sorted keys, no whitespace, no floats
with platform-dependent repr), SHA-256 digests, and a chained receipt log.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Sequence, Tuple

from .errors import InputError, IntegrityError

SCHEMA = "skeleton.gameforge.conductor_manifest.v1"
GENESIS = "0" * 64


def _normalize(value: Any) -> Any:
    if isinstance(value, Mapping):
        out = {}
        for k in value:
            if not isinstance(k, str):
                raise InputError(f"manifest keys must be str, got {type(k).__name__}")
            out[k] = _normalize(value[k])
        return out
    if isinstance(value, (list, tuple)):
        return [_normalize(v) for v in value]
    if isinstance(value, (set, frozenset)):
        return sorted(_normalize(v) for v in value)
    if isinstance(value, bool) or value is None or isinstance(value, (int, str)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise InputError("non-finite float in manifest")
        return format(value, ".9g")
    if hasattr(value, "to_dict"):
        return _normalize(value.to_dict())
    raise InputError(f"unsupported manifest value type {type(value).__name__}")


def canonical_json(value: Any) -> str:
    return json.dumps(_normalize(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("ascii")).hexdigest()


def chain(prev: str, payload_digest: str) -> str:
    return hashlib.sha256(f"{prev}:{payload_digest}".encode("ascii")).hexdigest()


@dataclass(frozen=True)
class Receipt:
    index: int
    step: str
    era: str
    payload_digest: str
    prev: str
    link: str

    def to_dict(self) -> Dict[str, Any]:
        return {"index": self.index, "step": self.step, "era": self.era,
                "payload_digest": self.payload_digest, "prev": self.prev, "link": self.link}


@dataclass
class ReceiptLog:
    receipts: List[Receipt] = field(default_factory=list)

    @property
    def head(self) -> str:
        return self.receipts[-1].link if self.receipts else GENESIS

    def append(self, step: str, era: str, payload: Any) -> Receipt:
        pd = digest(payload)
        r = Receipt(len(self.receipts), step, era, pd, self.head, chain(self.head, pd))
        self.receipts.append(r)
        return r

    def verify(self) -> None:
        prev = GENESIS
        for i, r in enumerate(self.receipts):
            if r.index != i or r.prev != prev or r.link != chain(prev, r.payload_digest):
                raise IntegrityError(f"receipt chain broken at index {i}", step=r.step)
            prev = r.link


@dataclass(frozen=True)
class Manifest:
    game_id: str
    era: str
    steps: Tuple[str, ...]
    artifacts: Tuple[Tuple[str, str], ...]  # (path, sha256) sorted by path
    receipts: Tuple[Receipt, ...]
    metadata: Tuple[Tuple[str, str], ...] = ()

    def body(self) -> Dict[str, Any]:
        return {
            "schema": SCHEMA,
            "game_id": self.game_id,
            "era": self.era,
            "steps": list(self.steps),
            "artifacts": [{"path": p, "sha256": h} for p, h in self.artifacts],
            "receipts": [r.to_dict() for r in self.receipts],
            "metadata": {k: v for k, v in self.metadata},
        }

    @property
    def manifest_digest(self) -> str:
        return digest(self.body())

    def to_dict(self) -> Dict[str, Any]:
        b = self.body()
        b["manifest_digest"] = self.manifest_digest
        return b

    def to_json(self) -> str:
        return canonical_json(self.to_dict())


def build_manifest(game_id: str, era: str, steps: Sequence[str], artifacts: Mapping[str, bytes],
                   log: ReceiptLog, metadata: Mapping[str, str] | None = None) -> Manifest:
    log.verify()
    arts = tuple(sorted((p, hashlib.sha256(b).hexdigest()) for p, b in artifacts.items()))
    meta = tuple(sorted((str(k), str(v)) for k, v in (metadata or {}).items()))
    return Manifest(game_id, era, tuple(steps), arts, tuple(log.receipts), meta)


def verify_manifest(data: Mapping[str, Any], artifacts: Mapping[str, bytes] | None = None) -> None:
    """Re-derive the digest of a serialized manifest and optionally its artifacts."""
    if data.get("schema") != SCHEMA:
        raise IntegrityError("manifest schema mismatch", detail={"schema": data.get("schema")})
    claimed = data.get("manifest_digest")
    body = {k: v for k, v in data.items() if k != "manifest_digest"}
    if digest(body) != claimed:
        raise IntegrityError("manifest digest mismatch")
    prev = GENESIS
    for i, r in enumerate(body.get("receipts", [])):
        if r["prev"] != prev or r["link"] != chain(prev, r["payload_digest"]) or r["index"] != i:
            raise IntegrityError(f"manifest receipt chain broken at {i}")
        prev = r["link"]
    if artifacts is not None:
        listed = {a["path"]: a["sha256"] for a in body.get("artifacts", [])}
        if set(listed) != set(artifacts):
            raise IntegrityError("artifact set mismatch", detail={"missing": sorted(set(listed) ^ set(artifacts))})
        for p, b in artifacts.items():
            if hashlib.sha256(b).hexdigest() != listed[p]:
                raise IntegrityError(f"artifact {p} digest mismatch")
