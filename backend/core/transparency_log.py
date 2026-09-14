"""Append-only Merkle transparency log with inclusion and extension proofs.

The log is intentionally generic. Entries are canonical JSON objects, committed as
RFC6962-style domain-separated leaf/node hashes. Extension proofs use the prior
binary frontier plus appended leaf hashes: an observer that pinned the old root can
verify that a newer root is an append-only extension without trusting the server's
mutable storage.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
from typing import Any, Iterable

from core.file_lease import FileLease

LOG_VERSION = 1
PROOF_VERSION = 1
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class TransparencyIntegrityError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class TransparencyEntry:
    version: int
    index: int
    payload: dict[str, Any]
    observed_at: str
    leaf_sha256: str


@dataclass(frozen=True, slots=True)
class InclusionProof:
    version: int
    index: int
    tree_size: int
    leaf_sha256: str
    siblings: tuple[str | None, ...]
    root_sha256: str


@dataclass(frozen=True, slots=True)
class FrontierConsistencyProof:
    version: int
    old_size: int
    new_size: int
    old_root_sha256: str
    new_root_sha256: str
    old_frontier: tuple[tuple[int, str], ...]
    appended_leaf_hashes: tuple[str, ...]


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def leaf_hash(payload: Any) -> str:
    return _hash(b"\x00" + _canonical(payload))


def node_hash(left: str, right: str) -> str:
    if not _SHA256.fullmatch(str(left)) or not _SHA256.fullmatch(str(right)):
        raise ValueError("merkle node children must be sha256")
    return _hash(b"\x01" + bytes.fromhex(left) + bytes.fromhex(right))


def _frontier_append(frontier: dict[int, str], size: int, leaf: str) -> tuple[dict[int, str], int]:
    if size < 0 or not _SHA256.fullmatch(str(leaf)):
        raise ValueError("invalid frontier append")
    out = dict(frontier); level = 0; current = leaf; n = size
    while n & 1:
        left = out.pop(level, None)
        if left is None:
            raise ValueError("frontier does not match tree size")
        current = node_hash(left, current); level += 1; n >>= 1
    out[level] = current
    return out, size + 1


def frontier_from_hashes(hashes: Iterable[str]) -> tuple[int, dict[int, str]]:
    frontier: dict[int, str] = {}; size = 0
    for digest in hashes:
        frontier, size = _frontier_append(frontier, size, digest)
    return size, frontier


def root_from_frontier(size: int, frontier: dict[int, str]) -> str:
    if size == 0:
        return _hash(b"")
    expected_levels = {level for level in range(size.bit_length()) if (size >> level) & 1}
    if set(frontier) != expected_levels:
        raise ValueError("frontier does not match tree size")
    acc: str | None = None
    for level in sorted(frontier, reverse=True):
        acc = frontier[level] if acc is None else node_hash(acc, frontier[level])
    if acc is None:
        raise ValueError("non-empty tree has empty frontier")
    return acc


def merkle_root(hashes: Iterable[str]) -> str:
    size, frontier = frontier_from_hashes(hashes)
    return root_from_frontier(size, frontier)


def _validate_hash(value: str) -> bool:
    return bool(_SHA256.fullmatch(str(value)))


def verify_inclusion(proof: InclusionProof) -> bool:
    if proof.version != PROOF_VERSION or proof.tree_size < 1 or not 0 <= proof.index < proof.tree_size:
        return False
    if not _validate_hash(proof.leaf_sha256) or not _validate_hash(proof.root_sha256):
        return False
    current = proof.leaf_sha256; index = proof.index; width = proof.tree_size; cursor = 0
    while width > 1:
        if cursor >= len(proof.siblings):
            return False
        sibling = proof.siblings[cursor]; sibling_exists = (index ^ 1) < width
        if sibling_exists:
            if sibling is None or not _validate_hash(sibling):
                return False
            current = node_hash(current, sibling) if index % 2 == 0 else node_hash(sibling, current)
        elif sibling is not None:
            return False
        index //= 2; width = (width + 1) // 2; cursor += 1
    return cursor == len(proof.siblings) and hmac.compare_digest(current, proof.root_sha256)


def verify_consistency(proof: FrontierConsistencyProof) -> bool:
    if proof.version != PROOF_VERSION or proof.old_size < 0 or proof.new_size < proof.old_size:
        return False
    if proof.new_size - proof.old_size != len(proof.appended_leaf_hashes):
        return False
    if not _validate_hash(proof.old_root_sha256) or not _validate_hash(proof.new_root_sha256):
        return False
    frontier: dict[int, str] = {}
    try:
        for level, digest in proof.old_frontier:
            level = int(level)
            if level < 0 or level in frontier or not _validate_hash(digest):
                return False
            frontier[level] = digest
        old_root = root_from_frontier(proof.old_size, frontier)
        if not hmac.compare_digest(old_root, proof.old_root_sha256):
            return False
        size = proof.old_size
        for digest in proof.appended_leaf_hashes:
            if not _validate_hash(digest):
                return False
            frontier, size = _frontier_append(frontier, size, digest)
        if size != proof.new_size:
            return False
        return hmac.compare_digest(root_from_frontier(size, frontier), proof.new_root_sha256)
    except (TypeError, ValueError):
        return False


class TransparencyLog:
    def __init__(self, root: str | Path, *, log_id: str = "epistemic-checkpoints") -> None:
        self.root = Path(root); self.root.mkdir(parents=True, exist_ok=True)
        self.log_id = str(log_id).strip()
        if not self.log_id:
            raise ValueError("log_id is required")
        self.path = self.root / "transparency-log.jsonl"
        self._lease = FileLease(self.root / ".transparency.lock")
        with self._lease.acquire():
            if not self.path.exists(): self.path.touch()
            self._load_verified()

    @staticmethod
    def _restore(raw: dict[str, Any]) -> TransparencyEntry:
        return TransparencyEntry(
            version=int(raw["version"]), index=int(raw["index"]),
            payload=dict(raw["payload"]), observed_at=str(raw["observed_at"]),
            leaf_sha256=str(raw["leaf_sha256"]),
        )

    def _load_verified(self) -> tuple[TransparencyEntry, ...]:
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise TransparencyIntegrityError("transparency log unreadable") from exc
        rows: list[TransparencyEntry] = []
        for raw_index, line in enumerate(lines):
            if not line.strip(): continue
            try: entry = self._restore(json.loads(line))
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                raise TransparencyIntegrityError("transparency log malformed") from exc
            if entry.version != LOG_VERSION or entry.index != len(rows):
                raise TransparencyIntegrityError("transparency sequence/version mismatch")
            expected = leaf_hash(entry.payload)
            if not hmac.compare_digest(expected, entry.leaf_sha256):
                raise TransparencyIntegrityError("transparency leaf hash mismatch")
            rows.append(entry)
        return tuple(rows)

    def append(self, payload: dict[str, Any], *, observed_at: str | None = None) -> TransparencyEntry:
        if not isinstance(payload, dict) or not payload:
            raise ValueError("transparency payload must be a non-empty object")
        stamp = observed_at or datetime.now(UTC).isoformat(); digest = leaf_hash(payload)
        with self._lease.acquire():
            rows = self._load_verified()
            for row in rows:
                if hmac.compare_digest(row.leaf_sha256, digest) and row.payload == payload:
                    return row
            entry = TransparencyEntry(LOG_VERSION, len(rows), dict(payload), stamp, digest)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(asdict(entry), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
                handle.flush(); os.fsync(handle.fileno())
            return entry

    def snapshot(self) -> tuple[TransparencyEntry, ...]:
        with self._lease.acquire(): return self._load_verified()

    def descriptor(self) -> dict[str, Any]:
        rows = self.snapshot(); hashes = [row.leaf_sha256 for row in rows]
        return {"version": LOG_VERSION, "log_id": self.log_id, "tree_size": len(rows),
                "root_sha256": merkle_root(hashes), "head_leaf_sha256": hashes[-1] if hashes else "",
                "verified": True, "cross_process_locking": True, "lock_backend": self._lease.backend}

    def inclusion(self, index: int) -> InclusionProof:
        rows = self.snapshot(); n = len(rows)
        if not 0 <= index < n: raise IndexError(index)
        layer = [row.leaf_sha256 for row in rows]; cursor = index; siblings: list[str | None] = []
        while len(layer) > 1:
            sibling_index = cursor ^ 1
            siblings.append(layer[sibling_index] if sibling_index < len(layer) else None)
            next_layer: list[str] = []
            for i in range(0, len(layer), 2):
                next_layer.append(node_hash(layer[i], layer[i + 1]) if i + 1 < len(layer) else layer[i])
            cursor //= 2; layer = next_layer
        return InclusionProof(PROOF_VERSION, index, n, rows[index].leaf_sha256, tuple(siblings), layer[0])

    def consistency(self, old_size: int) -> FrontierConsistencyProof:
        rows = self.snapshot(); hashes = [row.leaf_sha256 for row in rows]; new_size = len(hashes)
        if not 0 <= old_size <= new_size: raise ValueError("old_size must be within current tree")
        _, frontier = frontier_from_hashes(hashes[:old_size])
        return FrontierConsistencyProof(
            PROOF_VERSION, old_size, new_size, merkle_root(hashes[:old_size]), merkle_root(hashes),
            tuple(sorted(frontier.items())), tuple(hashes[old_size:]),
        )
