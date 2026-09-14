"""Tamper-evident source lineage graph for empirical knowledge.

Evidence does not exist in isolation. A secondary analysis, mirror, derivative
report, or synthesized dataset can inherit defects from an upstream source.
This registry records source ancestry explicitly so a retraction can propagate
through descendants without deleting historical evidence.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import Any, Iterable

from core.file_lease import FileLease


LINEAGE_VERSION = 1


class SourceLineageIntegrityError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class SourceNode:
    source_id: str
    source_kind: str
    locator: str
    parent_ids: tuple[str, ...]
    content_sha256: str
    registered_at: str
    retracted: bool = False
    retraction_reason: str = ""
    retracted_at: str = ""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


class SourceLineageGraph:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root); self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "source-lineage.json"
        self._lease = FileLease(self.root / ".source-lineage.lock")
        with self._lease.acquire():
            if not self.path.exists(): self._write({})
            else: self._load()

    @staticmethod
    def _checksum(nodes: dict[str, dict[str, Any]]) -> str:
        return _sha({"version": LINEAGE_VERSION, "nodes": nodes})

    def _load(self) -> dict[str, dict[str, Any]]:
        try: envelope = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SourceLineageIntegrityError("source lineage unreadable") from exc
        nodes = envelope.get("nodes"); checksum = envelope.get("sha256")
        if envelope.get("version") != LINEAGE_VERSION:
            raise SourceLineageIntegrityError("unsupported source lineage version")
        if not isinstance(nodes, dict) or not isinstance(checksum, str):
            raise SourceLineageIntegrityError("source lineage malformed")
        if not hmac.compare_digest(checksum, self._checksum(nodes)):
            raise SourceLineageIntegrityError("source lineage checksum mismatch")
        return {str(k): dict(v) for k, v in nodes.items() if isinstance(v, dict)}

    def _write(self, nodes: dict[str, dict[str, Any]]) -> None:
        envelope = {"version": LINEAGE_VERSION, "nodes": nodes, "sha256": self._checksum(nodes)}
        temp = self.path.with_suffix(f".{os.getpid()}.tmp")
        try:
            with temp.open("wb") as handle:
                handle.write(_canonical(envelope)); handle.flush(); os.fsync(handle.fileno())
            os.replace(temp, self.path)
        finally: temp.unlink(missing_ok=True)

    @staticmethod
    def _restore(raw: dict[str, Any]) -> SourceNode:
        return SourceNode(
            source_id=str(raw["source_id"]), source_kind=str(raw.get("source_kind", "unknown")),
            locator=str(raw.get("locator", "")), parent_ids=tuple(raw.get("parent_ids", ())),
            content_sha256=str(raw.get("content_sha256", "")), registered_at=str(raw["registered_at"]),
            retracted=bool(raw.get("retracted", False)), retraction_reason=str(raw.get("retraction_reason", "")),
            retracted_at=str(raw.get("retracted_at", "")),
        )

    def register(self, source_id: str, *, source_kind: str, locator: str = "", parent_ids: Iterable[str] = (),
                 content_sha256: str = "", registered_at: str | None = None) -> SourceNode:
        source_id = str(source_id).strip(); source_kind = str(source_kind).strip() or "unknown"
        parents = tuple(dict.fromkeys(str(x).strip() for x in parent_ids if str(x).strip()))
        if not source_id: raise ValueError("source_id required")
        if source_id in parents: raise ValueError("source cannot depend on itself")
        if content_sha256 and (len(content_sha256) != 64 or any(c not in "0123456789abcdefABCDEF" for c in content_sha256)):
            raise ValueError("content_sha256 must be a 64-character hex digest")
        stamp = registered_at or datetime.now(UTC).isoformat()
        with self._lease.acquire():
            nodes = self._load()
            missing = [p for p in parents if p not in nodes]
            if missing: raise ValueError(f"unknown parent source(s): {', '.join(missing)}")
            candidate = SourceNode(source_id, source_kind[:120], str(locator)[:2000], parents, content_sha256.lower(), stamp)
            existing = nodes.get(source_id)
            if existing is not None:
                restored = self._restore(existing)
                immutable = (restored.source_kind, restored.locator, restored.parent_ids, restored.content_sha256)
                wanted = (candidate.source_kind, candidate.locator, candidate.parent_ids, candidate.content_sha256)
                if immutable != wanted: raise SourceLineageIntegrityError("source identity collision")
                return restored
            nodes[source_id] = asdict(candidate); self._write(nodes); return candidate

    def get(self, source_id: str) -> SourceNode | None:
        with self._lease.acquire(): raw = self._load().get(source_id)
        return self._restore(raw) if raw else None

    @staticmethod
    def _descendant_ids(nodes: dict[str, dict[str, Any]], roots: set[str]) -> set[str]:
        affected = set(roots); changed = True
        while changed:
            changed = False
            for sid, raw in nodes.items():
                if sid not in affected and any(parent in affected for parent in raw.get("parent_ids", ())):
                    affected.add(sid); changed = True
        return affected

    def descendants(self, source_id: str, *, include_self: bool = False) -> tuple[SourceNode, ...]:
        with self._lease.acquire(): nodes = self._load()
        if source_id not in nodes: return ()
        ids = self._descendant_ids(nodes, {source_id})
        if not include_self: ids.discard(source_id)
        return tuple(self._restore(nodes[sid]) for sid in sorted(ids))

    def retract(self, source_id: str, reason: str, *, cascade: bool = True, retracted_at: str | None = None) -> tuple[str, ...]:
        reason = " ".join(str(reason).split()).strip()
        if not reason: raise ValueError("retraction reason required")
        stamp = retracted_at or datetime.now(UTC).isoformat()
        with self._lease.acquire():
            nodes = self._load()
            if source_id not in nodes: return ()
            affected = self._descendant_ids(nodes, {source_id}) if cascade else {source_id}
            for sid in affected:
                raw = nodes[sid]
                raw["retracted"] = True
                raw["retraction_reason"] = reason[:2000] if sid == source_id else f"upstream retraction: {source_id} — {reason[:1800]}"
                raw["retracted_at"] = stamp
                nodes[sid] = raw
            self._write(nodes)
        return tuple(sorted(affected))

    def active(self, source_id: str) -> bool:
        node = self.get(source_id)
        return bool(node is not None and not node.retracted)

    def stats(self) -> dict[str, Any]:
        with self._lease.acquire(): nodes = self._load()
        return {
            "version": LINEAGE_VERSION, "sources": len(nodes),
            "retracted": sum(1 for x in nodes.values() if x.get("retracted")),
            "edges": sum(len(x.get("parent_ids", ())) for x in nodes.values()),
            "sha256": self._checksum(nodes), "cross_process_locking": True, "lock_backend": self._lease.backend,
        }
