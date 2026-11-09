"""Deterministic sparse-Merkle commitments for portable state proofs.

The tree is keyed by SHA-256(key) over a fixed 256-bit address space. Missing
leaves have a deterministic default hash, so the same proof primitive verifies
both membership and non-membership without trusting a database lookup.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import re
from typing import Any, Mapping

TREE_VERSION = 1
DEPTH = 256
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def key_digest(key: str) -> str:
    normalized = " ".join(str(key).split()).strip()
    if not normalized:
        raise ValueError("merkle key is required")
    # Cryptographic identity must preserve exact normalized claim text. Semantic
    # equivalence/case folding belongs to ClaimIdentityEngine, never the address layer.
    return _hash(normalized.encode("utf-8"))


def _value_digest(value: Any) -> str:
    return _hash(_canonical(value))


def _leaf_hash(key_sha256: str, value: Any) -> str:
    return _hash(b"\x00" + bytes.fromhex(key_sha256) + bytes.fromhex(_value_digest(value)))


def _branch_hash(left: str, right: str) -> str:
    return _hash(b"\x01" + bytes.fromhex(left) + bytes.fromhex(right))


def _defaults() -> tuple[str, ...]:
    rows = [_hash(b"\x02")]
    for _ in range(DEPTH):
        rows.append(_branch_hash(rows[-1], rows[-1]))
    return tuple(rows)


_DEFAULTS = _defaults()
EMPTY_ROOT = _DEFAULTS[DEPTH]


@dataclass(frozen=True, slots=True)
class SparseMerkleProof:
    version: int
    key: str
    key_sha256: str
    present: bool
    value: Any | None
    siblings: tuple[str, ...]
    root_sha256: str


def _bits(key_sha256: str) -> tuple[int, ...]:
    raw = bytes.fromhex(key_sha256)
    return tuple((byte >> shift) & 1 for byte in raw for shift in range(7, -1, -1))


def _level_nodes(values: Mapping[str, Any]) -> list[dict[int, str]]:
    leaves: dict[int, str] = {}
    for key, value in values.items():
        digest = key_digest(key)
        position = int(digest, 16)
        leaf = _leaf_hash(digest, value)
        prior = leaves.get(position)
        if prior is not None and prior != leaf:
            raise ValueError("sparse merkle key digest collision")
        leaves[position] = leaf
    levels: list[dict[int, str]] = [leaves]
    current = leaves
    for depth in range(DEPTH):
        parents: dict[int, str] = {}
        parent_positions = {position >> 1 for position in current}
        default = _DEFAULTS[depth]
        for parent in parent_positions:
            left = current.get(parent << 1, default)
            right = current.get((parent << 1) | 1, default)
            digest = _branch_hash(left, right)
            if digest != _DEFAULTS[depth + 1]:
                parents[parent] = digest
        levels.append(parents)
        current = parents
    return levels


def sparse_merkle_root(values: Mapping[str, Any]) -> str:
    levels = _level_nodes(values)
    return levels[DEPTH].get(0, EMPTY_ROOT)


def build_sparse_proof(values: Mapping[str, Any], key: str) -> SparseMerkleProof:
    normalized = " ".join(str(key).split()).strip()
    digest = key_digest(normalized)
    position = int(digest, 16)
    levels = _level_nodes(values)
    siblings: list[str] = []
    current = position
    for depth in range(DEPTH):
        siblings.append(levels[depth].get(current ^ 1, _DEFAULTS[depth]))
        current >>= 1
    return SparseMerkleProof(
        version=TREE_VERSION,
        key=normalized,
        key_sha256=digest,
        present=normalized in values,
        value=values.get(normalized),
        siblings=tuple(siblings),
        root_sha256=levels[DEPTH].get(0, EMPTY_ROOT),
    )


def verify_sparse_proof(proof: SparseMerkleProof) -> bool:
    if proof.version != TREE_VERSION or len(proof.siblings) != DEPTH:
        return False
    if not _SHA256.fullmatch(str(proof.root_sha256)) or not _SHA256.fullmatch(str(proof.key_sha256)):
        return False
    if key_digest(proof.key) != proof.key_sha256:
        return False
    if any(not _SHA256.fullmatch(str(item)) for item in proof.siblings):
        return False
    current = _leaf_hash(proof.key_sha256, proof.value) if proof.present else _DEFAULTS[0]
    bits = _bits(proof.key_sha256)
    # Siblings are leaf-to-root; key bits are root-to-leaf.
    for depth, sibling in enumerate(proof.siblings):
        bit = bits[DEPTH - 1 - depth]
        current = _branch_hash(current, sibling) if bit == 0 else _branch_hash(sibling, current)
    return hmac.compare_digest(current, proof.root_sha256)


def proof_from_dict(raw: Mapping[str, Any]) -> SparseMerkleProof:
    return SparseMerkleProof(
        version=int(raw.get("version", 0)), key=str(raw.get("key", "")), key_sha256=str(raw.get("key_sha256", "")),
        present=bool(raw.get("present", False)), value=raw.get("value"),
        siblings=tuple(str(x) for x in raw.get("siblings", ())), root_sha256=str(raw.get("root_sha256", "")),
    )
