"""Canonical serialization and drift comparison for repository machine manifests."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import tempfile
import os
import stat
from typing import Mapping

from .model import RepositoryModel, canonical_json

MAX_MANIFEST_BYTES = 32 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class ManifestDelta:
    added_zones: tuple[str, ...]
    removed_zones: tuple[str, ...]
    changed_zones: tuple[str, ...]
    added_edges: tuple[str, ...]
    removed_edges: tuple[str, ...]
    finding_delta: int
    unclassified_delta: int
    fingerprint_changed: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "added_zones": list(self.added_zones),
            "removed_zones": list(self.removed_zones),
            "changed_zones": list(self.changed_zones),
            "added_edges": list(self.added_edges),
            "removed_edges": list(self.removed_edges),
            "finding_delta": self.finding_delta,
            "unclassified_delta": self.unclassified_delta,
            "fingerprint_changed": self.fingerprint_changed,
        }


def _checksum(state: object) -> str:
    return hashlib.sha256(canonical_json(state).encode("utf-8")).hexdigest()


def manifest_envelope(model: RepositoryModel, *, include_files: bool = True) -> dict[str, object]:
    state = model.as_dict(include_files=include_files)
    return {
        "format": "skeleton-repository-machine-manifest",
        "version": 1,
        "checksum": _checksum(state),
        "fingerprint": model.fingerprint,
        "state": state,
    }


def save_manifest(model: RepositoryModel, path: str | Path, *, include_files: bool = True) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    rendered = canonical_json(manifest_envelope(model, include_files=include_files)) + "\n"
    if len(rendered.encode("utf-8")) > MAX_MANIFEST_BYTES:
        raise ValueError("machine manifest exceeds byte budget")
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent, text=True
    )
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, destination)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise


def load_manifest(path: str | Path) -> Mapping[str, object]:
    source = Path(path)
    try:
        metadata = source.lstat()
    except OSError as exc:
        raise ValueError("machine manifest is unavailable") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ValueError("machine manifest must be a regular non-symlink file")
    if metadata.st_size <= 0 or metadata.st_size > MAX_MANIFEST_BYTES:
        raise ValueError("machine manifest exceeds byte budget")

    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(source, flags)
    except OSError as exc:
        raise ValueError("machine manifest cannot be opened safely") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("machine manifest must be a regular file")
        if before.st_size <= 0 or before.st_size > MAX_MANIFEST_BYTES:
            raise ValueError("machine manifest exceeds byte budget")
        with os.fdopen(fd, "rb", closefd=False) as handle:
            raw = handle.read(MAX_MANIFEST_BYTES + 1)
        after = os.fstat(fd)
        if (
            before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
        ):
            raise ValueError("machine manifest changed during read")
        if len(raw) > MAX_MANIFEST_BYTES:
            raise ValueError("machine manifest exceeds byte budget")
    finally:
        os.close(fd)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("machine manifest is invalid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("machine manifest must be an object")
    if payload.get("format") != "skeleton-repository-machine-manifest" or payload.get("version") != 1:
        raise ValueError("unsupported machine manifest format")
    state = payload.get("state")
    if not isinstance(state, dict):
        raise ValueError("machine manifest state missing")
    if payload.get("checksum") != _checksum(state):
        raise ValueError("machine manifest checksum mismatch")
    return payload


def _zones(state: Mapping[str, object]) -> dict[str, str]:
    result: dict[str, str] = {}
    raw = state.get("subsystems", [])
    if not isinstance(raw, list):
        return result
    for item in raw:
        if isinstance(item, dict) and isinstance(item.get("name"), str):
            result[item["name"]] = _checksum(item)
    return result


def _edges(state: Mapping[str, object]) -> set[str]:
    result: set[str] = set()
    raw = state.get("edges", [])
    if not isinstance(raw, list):
        return result
    for item in raw:
        if not isinstance(item, dict):
            continue
        source, target, kind = item.get("source"), item.get("target"), item.get("kind")
        if all(isinstance(value, str) for value in (source, target, kind)):
            result.add(f"{source}->{target}:{kind}")
    return result


def compare_manifest_states(before: Mapping[str, object], after: Mapping[str, object]) -> ManifestDelta:
    before_zones = _zones(before)
    after_zones = _zones(after)
    before_edges = _edges(before)
    after_edges = _edges(after)
    shared = set(before_zones) & set(after_zones)
    before_findings = before.get("findings", [])
    after_findings = after.get("findings", [])
    before_unclassified = before.get("unclassified_count", 0)
    after_unclassified = after.get("unclassified_count", 0)
    return ManifestDelta(
        added_zones=tuple(sorted(set(after_zones) - set(before_zones))),
        removed_zones=tuple(sorted(set(before_zones) - set(after_zones))),
        changed_zones=tuple(sorted(name for name in shared if before_zones[name] != after_zones[name])),
        added_edges=tuple(sorted(after_edges - before_edges)),
        removed_edges=tuple(sorted(before_edges - after_edges)),
        finding_delta=(len(after_findings) if isinstance(after_findings, list) else 0) - (len(before_findings) if isinstance(before_findings, list) else 0),
        unclassified_delta=(after_unclassified if isinstance(after_unclassified, int) else 0) - (before_unclassified if isinstance(before_unclassified, int) else 0),
        fingerprint_changed=_checksum(before) != _checksum(after),
    )
