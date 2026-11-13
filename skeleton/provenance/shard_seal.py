"""Fail-closed shard seal for generated file trees.

Ported from the ``volume-forge-ledger`` sibling repo (``shard_seal.py`` and
``kernel.merkle_root``).  The original sealed 200 emitted ``shard_NNN.py``
modules by importing and running a sample of them.  This port keeps the
pattern -- an expected shard manifest, missing shards fail closed, a Merkle
root over shard leaves, a JSON seal written atomically -- but hashes file
bytes instead of executing generated code, so sealing is side-effect free.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence

__all__ = ["ShardSealError", "ShardSeal", "merkle_root", "seal_tree", "verify_seal", "shard_names"]

SEAL_VERSION = 1
MAX_SHARD_BYTES = 64 * 1024 * 1024


class ShardSealError(RuntimeError):
    """Raised when a tree cannot be sealed or a seal does not verify."""


def merkle_root(leaves: Sequence[bytes]) -> str:
    """SHA-256 Merkle root; odd nodes are promoted by duplication."""
    if not leaves:
        raise ShardSealError("no leaves")
    level = [hashlib.sha256(b"\x00" + leaf).digest() for leaf in leaves]
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [hashlib.sha256(b"\x01" + level[i] + level[i + 1]).digest()
                 for i in range(0, len(level), 2)]
    return level[0].hex()


def shard_names(count: int, prefix: str = "shard_", suffix: str = ".py") -> List[str]:
    if count <= 0:
        raise ShardSealError("count must be positive")
    width = max(3, len(str(count - 1)))
    return [f"{prefix}{i:0{width}d}{suffix}" for i in range(count)]


@dataclass(frozen=True)
class ShardSeal:
    expected: int
    digests: Dict[str, str]
    root: str
    version: int = SEAL_VERSION

    def to_json(self) -> str:
        return json.dumps({"version": self.version, "expected": self.expected,
                           "root": self.root, "digests": self.digests}, indent=2, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> "ShardSeal":
        try:
            raw = json.loads(text)
            seal = cls(int(raw["expected"]), dict(raw["digests"]), str(raw["root"]), int(raw["version"]))
        except (ValueError, KeyError, TypeError) as exc:
            raise ShardSealError(f"malformed seal: {exc}") from exc
        if seal.version != SEAL_VERSION:
            raise ShardSealError(f"unsupported seal version {seal.version}")
        return seal


def _digest(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ShardSealError(f"not a regular file: {path.name}")
    if path.stat().st_size > MAX_SHARD_BYTES:
        raise ShardSealError(f"shard too large: {path.name}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _collect(root: Path, names: Sequence[str]) -> Dict[str, str]:
    missing = [n for n in names if not (root / n).is_file()]
    if missing:
        head = ", ".join(missing[:5])
        raise ShardSealError(f"{len(missing)} missing shard(s): {head}")
    return {n: _digest(root / n) for n in names}


def _root_of(digests: Dict[str, str]) -> str:
    return merkle_root([f"{n}|{d}".encode() for n, d in sorted(digests.items())])


def seal_tree(root: Path, names: Sequence[str], dest: Path | None = None) -> ShardSeal:
    """Seal ``names`` under ``root``. Any missing shard fails closed."""
    if len(set(names)) != len(names):
        raise ShardSealError("duplicate shard names")
    digests = _collect(Path(root), names)
    seal = ShardSeal(len(names), digests, _root_of(digests))
    if dest is not None:
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".tmp")
        tmp.write_text(seal.to_json(), encoding="utf-8")
        os.replace(tmp, dest)
    return seal


def verify_seal(root: Path, seal: ShardSeal) -> None:
    """Raise unless every sealed shard exists with identical bytes."""
    if seal.expected != len(seal.digests):
        raise ShardSealError("seal count mismatch")
    if _root_of(seal.digests) != seal.root:
        raise ShardSealError("seal root does not match its digests")
    current = _collect(Path(root), sorted(seal.digests))
    changed = sorted(n for n, d in current.items() if seal.digests[n] != d)
    if changed:
        raise ShardSealError(f"{len(changed)} shard(s) changed: {', '.join(changed[:5])}")
