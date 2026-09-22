"""Append-only SHA-256 context ledger — the blockchain of helical turns.

Each block commits: previous hash, merkle of (watson|crick|stage|meta),
tensor fingerprint, snowball mass. verify() walks genesis → head and
refuses a mutated payload. This is not a cryptocurrency; it is an
audit spine for GameForge runs.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from skeleton.kernel.errors import SkeletonError


class LedgerError(SkeletonError):
    code = "CTX.LEDGER"
    http_status = 409


def _canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def merkle(leaves: List[str]) -> str:
    if not leaves:
        return sha256_hex(b"")
    layer = [sha256_hex(leaf.encode()) for leaf in leaves]
    while len(layer) > 1:
        if len(layer) % 2:
            layer.append(layer[-1])
        layer = [sha256_hex((layer[i] + layer[i + 1]).encode()) for i in range(0, len(layer), 2)]
    return layer[0]


GENESIS_HASH = "0" * 64


@dataclass
class Block:
    height: int
    prev: str
    merkle_root: str
    stage: str
    payload: Dict[str, Any]
    mass: float
    tensor_fp: str
    occurred_at: float
    hash: str = ""

    def digest_material(self) -> bytes:
        body = {
            "height": self.height,
            "prev": self.prev,
            "merkle_root": self.merkle_root,
            "stage": self.stage,
            "payload": self.payload,
            "mass": round(self.mass, 6),
            "tensor_fp": self.tensor_fp,
            "occurred_at": self.occurred_at,
        }
        return _canonical(body)

    def compute_hash(self) -> str:
        return sha256_hex(self.digest_material())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "height": self.height,
            "prev": self.prev,
            "hash": self.hash,
            "merkle_root": self.merkle_root,
            "stage": self.stage,
            "mass": self.mass,
            "tensor_fp": self.tensor_fp,
            "occurred_at": self.occurred_at,
            "payload": self.payload,
        }


@dataclass
class ContextLedger:
    chain: List[Block] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.chain:
            genesis = Block(
                height=0, prev=GENESIS_HASH, merkle_root=sha256_hex(b"genesis"),
                stage="genesis", payload={"note": "context ledger genesis"},
                mass=0.0, tensor_fp="", occurred_at=time.time(),
            )
            genesis.hash = genesis.compute_hash()
            self.chain.append(genesis)

    @property
    def head(self) -> Block:
        return self.chain[-1]

    @property
    def height(self) -> int:
        return self.chain[-1].height

    def append(self, stage: str, payload: Dict[str, Any], *,
               mass: float, tensor_fp: str,
               leaves: Optional[List[str]] = None) -> Block:
        leaves = leaves or [stage, json.dumps(payload, sort_keys=True, default=str)]
        block = Block(
            height=self.height + 1,
            prev=self.head.hash,
            merkle_root=merkle(leaves),
            stage=stage,
            payload=dict(payload),
            mass=mass,
            tensor_fp=tensor_fp,
            occurred_at=time.time(),
        )
        block.hash = block.compute_hash()
        self.chain.append(block)
        return block

    def verify(self) -> List[str]:
        problems: List[str] = []
        if not self.chain:
            return ["empty chain"]
        if self.chain[0].stage != "genesis":
            problems.append("missing genesis")
        for i, block in enumerate(self.chain):
            if block.hash != block.compute_hash():
                problems.append(f"hash mismatch at height {block.height}")
            if i == 0:
                continue
            prev = self.chain[i - 1]
            if block.prev != prev.hash:
                problems.append(f"broken link at height {block.height}")
            if block.height != prev.height + 1:
                problems.append(f"height skip at {block.height}")
        return problems

    def tamper(self, height: int, key: str, value: Any) -> None:
        """Test hook: mutate payload without recomputing hash."""
        self.chain[height].payload[key] = value

    def to_dict(self) -> Dict[str, Any]:
        return {
            "height": self.height,
            "head": self.head.hash,
            "valid": not self.verify(),
            "blocks": [b.to_dict() for b in self.chain],
        }
