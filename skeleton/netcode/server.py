"""B064 - dedicated headless server: deterministic tick loop, handshake, metrics.

Run: ``python -m skeleton.netcode --ticks 600 --tick-rate 30 --seed 7``.
Config precedence: CLI args > ``SKELETON_NET_*`` env vars > defaults.
No rendering, no GPU, no third-party deps: stdlib only (minimal artifact).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import struct
import time
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Optional

from .contracts import (MIN_COMPATIBLE_VERSION, PROTOCOL_VERSION, BinaryFrameCodec, FrameError, Message,
                        MessageKind, is_compatible)
from .replication import BandwidthBudget, ServerReplicator

_HELLO = struct.Struct(">HH")  # client protocol version, client min version
_ENV = "SKELETON_NET_"


@dataclass(frozen=True)
class ServerConfig:
    tick_rate: int = 30
    max_clients: int = 32
    seed: int = 0
    ticks: int = 0  # 0 = run until stopped
    bytes_per_tick: int = 1200
    entities: int = 16

    def __post_init__(self) -> None:
        if not 1 <= self.tick_rate <= 240 or not 1 <= self.max_clients <= 1024 or self.entities < 0:
            raise ValueError("invalid server config")

    @classmethod
    def from_sources(cls, argv: Optional[list[str]] = None, env: Optional[dict] = None) -> "ServerConfig":
        env = os.environ if env is None else env
        vals = {f.name: int(env[_ENV + f.name.upper()]) for f in fields(cls) if _ENV + f.name.upper() in env}
        p = argparse.ArgumentParser(prog="python -m skeleton.netcode", description="Skeleton headless server")
        for f in fields(cls):
            p.add_argument("--" + f.name.replace("_", "-"), type=int, default=None)
        p.add_argument("--manifest", action="store_true", help="print the reproducible build manifest and exit")
        ns = p.parse_args(argv or [])
        vals.update({k: v for k, v in vars(ns).items() if v is not None and k != "manifest"})
        cfg = cls(**vals)
        object.__setattr__(cfg, "_manifest", ns.manifest)
        return cfg


def build_manifest() -> dict:
    """Content hash of the server's own sources: same code => same manifest, byte for byte."""
    here = Path(__file__).resolve().parent
    files = sorted(p for p in here.glob("*.py"))
    h = hashlib.sha256()
    per = {}
    for p in files:
        d = p.read_bytes()
        per[p.name] = hashlib.sha256(d).hexdigest()
        h.update(p.name.encode() + b"\0" + d)
    return {"protocol_version": PROTOCOL_VERSION, "min_compatible_version": MIN_COMPATIBLE_VERSION,
            "files": per, "digest": h.hexdigest(), "dependencies": []}


def hello_payload(version: int = PROTOCOL_VERSION, min_version: int = MIN_COMPATIBLE_VERSION) -> bytes:
    return _HELLO.pack(version, min_version)


class HeadlessServer:
    """Transport-agnostic server. ``connect(cid, transport)`` adds a datagram endpoint."""

    def __init__(self, config: ServerConfig) -> None:
        self.config = config
        self.codec = BinaryFrameCodec()
        self.rng = random.Random(config.seed)
        self.repl = ServerReplicator(BandwidthBudget(config.bytes_per_tick))
        self.transports: dict[str, object] = {}
        self.accepted: set[str] = set()
        self.seq = 0
        self.metrics = {"ticks": 0, "clients": 0, "handshakes_ok": 0, "handshakes_rejected": 0,
                        "frames_in": 0, "frames_malformed": 0, "bytes_out": 0, "inputs": 0}
        for e in range(config.entities):
            self.repl.set(e, x=self.rng.randint(-100, 100), y=self.rng.randint(-100, 100), hp=100)

    def connect(self, cid: str, transport) -> None:
        self.transports[cid] = transport

    def _send(self, cid: str, kind: MessageKind, payload: bytes = b"") -> None:
        self.seq = (self.seq + 1) & 0xFFFFFFFF
        data = self.codec.encode(Message(kind, payload, seq=self.seq))
        self.metrics["bytes_out"] += len(data)
        self.transports[cid].send(data)

    def _handshake(self, cid: str, msg: Message) -> None:
        reason = None
        try:
            ver, cmin = _HELLO.unpack(msg.payload)
        except struct.error:
            ver, cmin, reason = msg.version, 0, b"malformed_hello"
        if reason is None and not (is_compatible(ver) and cmin <= PROTOCOL_VERSION):
            reason = b"incompatible_version"
        elif reason is None and len(self.accepted) >= self.config.max_clients:
            reason = b"server_full"
        if reason:
            self.metrics["handshakes_rejected"] += 1
            self._send(cid, MessageKind.REJECT, reason)
            self.transports.pop(cid, None)
            return
        self.accepted.add(cid)
        self.repl.add_client(cid)
        self.metrics["handshakes_ok"] += 1
        self._send(cid, MessageKind.WELCOME, _HELLO.pack(PROTOCOL_VERSION, MIN_COMPATIBLE_VERSION))

    def tick(self) -> None:
        for cid in list(self.transports):
            t = self.transports.get(cid)
            while t is not None and (raw := t.recv()) is not None:
                self.metrics["frames_in"] += 1
                try:
                    msg = self.codec.decode(raw)
                except FrameError:
                    self.metrics["frames_malformed"] += 1
                    continue
                if cid not in self.accepted:
                    if msg.kind is MessageKind.HELLO:
                        self._handshake(cid, msg)
                    t = self.transports.get(cid)
                    continue
                if msg.kind is MessageKind.ACK and len(msg.payload) == 4:
                    self.repl.ack(cid, struct.unpack(">I", msg.payload)[0])
                elif msg.kind is MessageKind.INPUT:
                    self.metrics["inputs"] += 1
                elif msg.kind is MessageKind.DISCONNECT:
                    self.accepted.discard(cid)
                    self.transports.pop(cid, None)
                    self.repl.clients.pop(cid, None)
                    t = None
        # deterministic simulation step
        for e in sorted(self.repl.state):
            s = self.repl.state[e]
            self.repl.set(e, x=s.get("x", 0) + self.rng.randint(-1, 1), y=s.get("y", 0) + self.rng.randint(-1, 1))
        self.repl.step()
        for cid in sorted(self.accepted):
            self._send(cid, MessageKind.SNAPSHOT, self.repl.snapshot_for(cid))
        self.metrics["ticks"] += 1
        self.metrics["clients"] = len(self.accepted)

    def state_digest(self) -> str:
        return hashlib.sha256(json.dumps(self.repl.state, sort_keys=True).encode()).hexdigest()

    def health(self) -> dict:
        return {"status": "ok", "protocol_version": PROTOCOL_VERSION, "tick": self.metrics["ticks"],
                "metrics": dict(self.metrics), "config": asdict(self.config)}

    def run(self, realtime: bool = True, max_ticks: Optional[int] = None) -> dict:
        n = max_ticks if max_ticks is not None else self.config.ticks
        period = 1.0 / self.config.tick_rate
        nxt = time.monotonic()
        i = 0
        while n == 0 or i < n:
            self.tick()
            i += 1
            if realtime:
                nxt += period
                delay = nxt - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
        return self.health()


def main(argv: Optional[list[str]] = None) -> int:
    cfg = ServerConfig.from_sources(argv)
    if getattr(cfg, "_manifest", False):
        print(json.dumps(build_manifest(), sort_keys=True))
        return 0
    if cfg.ticks == 0:
        raise SystemExit("--ticks is required for the bundled entry point (0 would run forever without a transport)")
    report = HeadlessServer(cfg).run(realtime=False)
    print(json.dumps(report, sort_keys=True))
    return 0
