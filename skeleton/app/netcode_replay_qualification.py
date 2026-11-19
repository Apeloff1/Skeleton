"""Profile and independently replay a bounded original headless netcode journey.

Uses actual canonical server, codec, in-memory transports, client replica,
seeded unreliable link and frame sampler. No sockets, native game engine,
kernel network, public endpoint or remote client is exercised.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import math
import struct
import sys
import time
from typing import Sequence

from skeleton.netcode.contracts import (
    BinaryFrameCodec, FRAME_OVERHEAD, MAX_PAYLOAD, Message, MessageKind,
)
from skeleton.netcode.replication import ClientReplica, LossyLink
from skeleton.netcode.server import HeadlessServer, ServerConfig, build_manifest, hello_payload
from skeleton.netcode.transport import InMemoryTransport
from skeleton.perf_profiler.frames import FrameSampler


class ReplayError(ValueError):
    pass


def _digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class ReplayPolicy:
    seed: int = 17
    ticks: int = 120
    clients: int = 4
    entities: int = 12
    loss_ppm: int = 150_000
    duplicate_ppm: int = 75_000
    delay_ticks: int = 3
    recovery_ticks: int = 12
    tick_rate: int = 60

    def __post_init__(self):
        for value, lo, hi in (
            (self.seed, 0, 2**32 - 1), (self.ticks, 1, 4096),
            (self.clients, 1, 16), (self.entities, 1, 32),
            (self.loss_ppm, 0, 1_000_000), (self.duplicate_ppm, 0, 1_000_000),
            (self.delay_ticks, 0, 16), (self.recovery_ticks, 2, 64),
            (self.tick_rate, 1, 240),
        ):
            if type(value) is not int or not lo <= value <= hi:
                raise ReplayError("invalid replay policy")
        if self.recovery_ticks < self.delay_ticks + 2:
            raise ReplayError("recovery must drain prior delayed snapshots")
        if (self.ticks + self.recovery_ticks) * self.clients * self.entities > 1_000_000:
            raise ReplayError("simulation work ceiling exceeded")


@dataclass
class _Peer:
    name: str
    client: InMemoryTransport
    server: InMemoryTransport
    replica: ClientReplica
    link: LossyLink
    welcomed: bool = False
    sequence: int = 1
    snapshots_sent: int = 0
    snapshots_delivered: int = 0
    acknowledgements: int = 0

    def write(self, codec, kind, payload=b""):
        self.sequence += 1
        self.client.send(codec.encode(Message(kind, payload, seq=self.sequence)))


def _run(policy):
    codec = BinaryFrameCodec()
    server = HeadlessServer(ServerConfig(
        tick_rate=policy.tick_rate, max_clients=policy.clients,
        seed=policy.seed, bytes_per_tick=MAX_PAYLOAD, entities=policy.entities,
    ))
    sampler = FrameSampler(budget_ms=1000.0 / policy.tick_rate,
                           capacity=policy.ticks + policy.recovery_ticks)
    peers = []
    transcript = sha256()
    wire_frames = 0
    wire_bytes = 0
    try:
        for index in range(policy.clients):
            c, s = InMemoryTransport.pair()
            name = f"client-{index:03d}"
            peer = _Peer(name, c, s, ClientReplica(), LossyLink(
                policy.seed + index + 1, policy.loss_ppm / 1_000_000,
                policy.duplicate_ppm / 1_000_000, policy.delay_ticks,
            ))
            peers.append(peer)
            server.connect(name, s)
            c.send(codec.encode(Message(MessageKind.HELLO, hello_payload(), seq=1)))
        for tick in range(policy.ticks + policy.recovery_ticks):
            start = time.perf_counter_ns()
            reliable = tick >= policy.ticks
            if tick:
                for peer in peers:
                    peer.write(codec, MessageKind.INPUT, struct.pack(">I", tick))
            server.tick()
            for peer in peers:
                direct = []
                frames_this_peer = 0
                while (raw := peer.client.recv()) is not None:
                    frames_this_peer += 1
                    wire_frames += 1
                    wire_bytes += len(raw)
                    if frames_this_peer > 2 or len(raw) > MAX_PAYLOAD + FRAME_OVERHEAD:
                        raise ReplayError("unexpected headless frame budget")
                    msg = codec.decode(raw)
                    transcript.update(struct.pack(">II", tick, len(raw)))
                    transcript.update(peer.name.encode() + raw)
                    if msg.kind is MessageKind.WELCOME:
                        if peer.welcomed:
                            raise ReplayError("duplicate initial welcome")
                        peer.welcomed = True
                    elif msg.kind is MessageKind.SNAPSHOT:
                        if not peer.welcomed:
                            raise ReplayError("snapshot before welcome")
                        peer.snapshots_sent += 1
                        if reliable:
                            direct.append(msg.payload)
                        else:
                            peer.link.send(msg.payload)
                    else:
                        raise ReplayError("unexpected server message")
                for payload in (*peer.link.advance(), *direct):
                    peer.snapshots_delivered += 1
                    transcript.update(peer.name.encode() + b"delivery" +
                                      struct.pack(">II", tick, len(payload)) + payload)
                    accepted = peer.replica.receive(payload)
                    if accepted is not None:
                        peer.acknowledgements += 1
                        peer.write(codec, MessageKind.ACK, struct.pack(">I", accepted))
            elapsed = time.perf_counter_ns() - start
            if elapsed < 0:
                raise ReplayError("monotonic measurement reversed")
            sampler.record(elapsed / 1_000_000)
        results = []
        for peer in peers:
            results.append({
                "client": peer.name,
                "welcomed": peer.welcomed,
                "snapshots_sent": peer.snapshots_sent,
                "snapshots_delivered": peer.snapshots_delivered,
                "acknowledgements": peer.acknowledgements,
                "rejected_snapshots": peer.replica.rejected,
                "converged": peer.replica.state == server.repl.state,
                "replica_digest": _digest(peer.replica.state),
            })
        deterministic = {
            "server_state_digest": server.state_digest(),
            "transcript_sha256": transcript.hexdigest(),
            "server_metrics": dict(server.metrics),
            "wire_frames_from_server": wire_frames,
            "wire_bytes_from_server": wire_bytes,
            "clients": results,
        }
        return deterministic, sampler.stats().to_dict()
    finally:
        for peer in peers:
            peer.client.close()
            peer.server.close()


def qualify(policy: ReplayPolicy, *, authorized: bool,
            max_hitch_ratio: float | None = None):
    if authorized is not True:
        raise PermissionError("explicit local qualification required")
    if not isinstance(policy, ReplayPolicy):
        raise ReplayError("invalid replay policy type")
    if max_hitch_ratio is not None and (
        type(max_hitch_ratio) not in (int, float)
        or not math.isfinite(max_hitch_ratio) or not 0 <= max_hitch_ratio <= 1
    ):
        raise ReplayError("invalid timing gate")
    before = build_manifest()
    first, timing_one = _run(policy)
    second, timing_two = _run(policy)
    after = build_manifest()
    if before != after:
        raise ReplayError("canonical netcode source changed between observations")
    same = first == second
    converged = all(row["welcomed"] and row["converged"] for row in first["clients"])
    timing_pass = None if max_hitch_ratio is None else all(
        t["hitch_ratio"] <= max_hitch_ratio for t in (timing_one, timing_two)
    )
    evidence = {
        "schema": "skeleton.local-netcode-replay.v1",
        "policy": asdict(policy),
        "netcode_source_manifest_digest": before["digest"],
        "deterministic_first": first,
        "deterministic_second_digest": _digest(second),
        "deterministic_replay_matched": same,
        "clients_converged": converged,
        "in_process_transport_executed": True,
        "native_engine_executed": False,
        "physical_network_tested": False,
        "release_certified": False,
    }
    return {**evidence, "deterministic_evidence_digest": _digest(evidence),
            "measured_tick_profile": [timing_one, timing_two],
            "timing_gate_limit": max_hitch_ratio, "timing_gate_passed": timing_pass,
            "local_qualification_passed": same and converged and timing_pass is not False}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for key, value in asdict(ReplayPolicy()).items():
        parser.add_argument("--" + key.replace("_", "-"), type=int, default=value)
    parser.add_argument("--max-hitch-ratio", type=float)
    parser.add_argument("--trusted-local-operator", action="store_true")
    args = parser.parse_args(argv)
    try:
        policy = ReplayPolicy(**{key: getattr(args, key) for key in asdict(ReplayPolicy())})
        result = qualify(policy, authorized=args.trusted_local_operator,
                         max_hitch_ratio=args.max_hitch_ratio)
    except (ReplayError, PermissionError, ValueError, OSError) as exc:
        print(json.dumps({"qualified": False, "error": type(exc).__name__}), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["local_qualification_passed"] else 3
