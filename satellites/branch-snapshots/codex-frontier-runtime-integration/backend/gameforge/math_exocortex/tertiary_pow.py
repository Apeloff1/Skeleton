from __future__ import annotations
"""
Tertiary sandbox — emulated Bitcoin PoW as MapReduce for math problem sharding.
Chunk large problems into blocks, mine (solve) shards, reassemble answers. Full logs.
"""

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple


@dataclass
class MathShard:
    shard_id: str
    index: int
    payload: Dict[str, Any]
    nonce: int = 0
    hash: str = ""
    solved: bool = False
    result: Any = None
    work_ms: float = 0.0


@dataclass
class Block:
    block_id: str
    height: int
    prev_hash: str
    shards: List[MathShard] = field(default_factory=list)
    merkle_root: str = ""
    mined: bool = False
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


class EmulatedMiner:
    """
    Toy PoW: find nonce such that sha256(header+nonce) starts with difficulty zeros.
    Used to pace/validate shard completion, not real crypto mining.
    """

    def __init__(self, difficulty: int = 2):
        self.difficulty = max(1, min(5, difficulty))
        self.logs: List[Dict[str, Any]] = []

    def mine(self, header: str, max_nonce: int = 500_000) -> Tuple[int, str, float]:
        prefix = "0" * self.difficulty
        t0 = time.perf_counter()
        for nonce in range(max_nonce):
            h = hashlib.sha256(f"{header}:{nonce}".encode()).hexdigest()
            if h.startswith(prefix):
                ms = (time.perf_counter() - t0) * 1000
                self.logs.append({"header": header[:64], "nonce": nonce, "hash": h, "ms": ms})
                return nonce, h, ms
        ms = (time.perf_counter() - t0) * 1000
        h = hashlib.sha256(f"{header}:fail".encode()).hexdigest()
        return -1, h, ms


def _merkle(hashes: List[str]) -> str:
    if not hashes:
        return hashlib.sha256(b"empty").hexdigest()
    layer = hashes[:]
    while len(layer) > 1:
        nxt = []
        for i in range(0, len(layer), 2):
            a = layer[i]
            b = layer[i + 1] if i + 1 < len(layer) else a
            nxt.append(hashlib.sha256(f"{a}{b}".encode()).hexdigest())
        layer = nxt
    return layer[0]


class TertiaryPoWSandbox:
    """
    MapReduce-style math via emulated blockchain:
      problem → shards → mine each shard (PoW + compute) → assemble block answer
    """

    def __init__(self, difficulty: int = 2):
        self.miner = EmulatedMiner(difficulty=difficulty)
        self.chain: List[Block] = []
        self.logs: List[Dict[str, Any]] = []
        self._genesis()

    def _genesis(self):
        g = Block(block_id="genesis", height=0, prev_hash="0" * 64, mined=True, merkle_root="genesis")
        self.chain.append(g)

    def _prev_hash(self) -> str:
        last = self.chain[-1]
        raw = json.dumps({"id": last.block_id, "merkle": last.merkle_root}, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()

    def shard_sum(self, numbers: List[float], chunk_size: int = 8) -> Dict[str, Any]:
        """Example MapReduce: distributed sum."""
        chunks = [numbers[i : i + chunk_size] for i in range(0, len(numbers), chunk_size)]
        return self._run_sharded(
            problem_type="sum",
            payloads=[{"values": c} for c in chunks],
            solve_fn=lambda p: float(sum(p["values"])),
            assemble_fn=lambda results: float(sum(results)),
        )

    def shard_map(
        self,
        items: List[Any],
        map_expr: str,
        chunk_size: int = 5,
    ) -> Dict[str, Any]:
        """
        map_expr uses x: e.g. 'x**2 + 1' evaluated safely per element.
        """
        from gameforge.math_exocortex.primary import SafeCalculator

        calc = SafeCalculator()

        def solve(p):
            out = []
            for x in p["values"]:
                out.append(calc.eval(map_expr.replace("x", f"({x})")))
            return out

        chunks = [items[i : i + chunk_size] for i in range(0, len(items), chunk_size)]
        return self._run_sharded(
            problem_type=f"map:{map_expr}",
            payloads=[{"values": c} for c in chunks],
            solve_fn=solve,
            assemble_fn=lambda results: [x for chunk in results for x in chunk],
        )

    def _run_sharded(
        self,
        problem_type: str,
        payloads: List[Dict[str, Any]],
        solve_fn: Callable[[Dict[str, Any]], Any],
        assemble_fn: Callable[[List[Any]], Any],
    ) -> Dict[str, Any]:
        height = len(self.chain)
        block = Block(
            block_id=str(uuid.uuid4())[:12],
            height=height,
            prev_hash=self._prev_hash(),
        )
        shard_hashes = []
        for i, payload in enumerate(payloads):
            sid = str(uuid.uuid4())[:10]
            header = f"{block.block_id}:{i}:{json.dumps(payload, sort_keys=True)[:120]}"
            t0 = time.perf_counter()
            try:
                result = solve_fn(payload)
                ok = True
                err = None
            except Exception as e:
                result = None
                ok = False
                err = str(e)
            nonce, h, mine_ms = self.miner.mine(header)
            work_ms = (time.perf_counter() - t0) * 1000
            shard = MathShard(
                shard_id=sid,
                index=i,
                payload=payload,
                nonce=nonce,
                hash=h,
                solved=ok and nonce >= 0,
                result=result,
                work_ms=work_ms,
            )
            block.shards.append(shard)
            shard_hashes.append(h)
            self.logs.append(
                {
                    "event": "shard_mined",
                    "block": block.block_id,
                    "shard": sid,
                    "ok": shard.solved,
                    "error": err,
                    "mine_ms": mine_ms,
                    "work_ms": work_ms,
                }
            )

        block.merkle_root = _merkle(shard_hashes)
        results = [s.result for s in block.shards if s.solved]
        try:
            answer = assemble_fn(results)
            assemble_ok = True
            assemble_err = None
        except Exception as e:
            answer = None
            assemble_ok = False
            assemble_err = str(e)

        block.mined = all(s.solved for s in block.shards) and assemble_ok
        self.chain.append(block)
        self.logs.append(
            {
                "event": "block_closed",
                "block": block.block_id,
                "height": block.height,
                "problem_type": problem_type,
                "shards": len(block.shards),
                "mined": block.mined,
                "answer": answer,
                "error": assemble_err,
            }
        )
        return {
            "ok": block.mined,
            "block_id": block.block_id,
            "height": block.height,
            "shards": len(block.shards),
            "merkle_root": block.merkle_root,
            "answer": answer,
            "error": assemble_err,
            "chain_length": len(self.chain),
        }

    def chain_status(self) -> Dict[str, Any]:
        return {
            "height": len(self.chain) - 1,
            "blocks": [
                {
                    "id": b.block_id,
                    "height": b.height,
                    "shards": len(b.shards),
                    "mined": b.mined,
                    "merkle": b.merkle_root[:16],
                }
                for b in self.chain[-10:]
            ],
            "miner_log_tail": self.miner.logs[-5:],
            "log_tail": self.logs[-10:],
        }
