"""Strict portable checkpoint codec for the canonical fixed-tick replay.

The codec does not write paths or claim atomic filesystem persistence. Callers
must provide their platform's durable, no-clobber storage implementation.
"""
from __future__ import annotations

from hashlib import sha256
import json

from skeleton.simulation.fixed_tick import (
    FixedTickReplay, InputEvent, ReplayError, ReplayFrame, MAX_EVENTS,
)

SCHEMA = "skeleton.game.replay-checkpoint.v1"
MAX_CHECKPOINT_BYTES = 8_000_000
_HEX = frozenset("0123456789abcdef")


def _hex_digest(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in _HEX for c in value)


def _int(value: object, low: int, high: int) -> bool:
    return type(value) is int and low <= value <= high


def encode(replay: FixedTickReplay) -> bytes:
    if not isinstance(replay, FixedTickReplay):
        raise ReplayError("checkpoint requires canonical replay")
    frames = [
        {"tick": f.tick, "prior": f.prior_digest, "digest": f.digest,
         "events": [{"tick": e.tick, "action": e.action, "pressed": e.pressed}
                    for e in f.events]}
        for f in replay.frames
    ]
    payload = {"schema": SCHEMA, "hz": replay.hz, "seed": replay.seed,
               "head": replay.digest, "frames": frames}
    data = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    if len(data) > MAX_CHECKPOINT_BYTES:
        raise ReplayError("checkpoint byte budget exhausted")
    return data


def decode(data: bytes) -> FixedTickReplay:
    if type(data) is not bytes or len(data) > MAX_CHECKPOINT_BYTES:
        raise ReplayError("checkpoint must be bounded bytes")
    try:
        obj = json.loads(data.decode("utf-8"), parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (UnicodeError, ValueError, TypeError, RecursionError) as exc:
        raise ReplayError("invalid checkpoint encoding") from exc
    if type(obj) is not dict or set(obj) != {"schema", "hz", "seed", "head", "frames"} or obj["schema"] != SCHEMA:
        raise ReplayError("invalid checkpoint schema")
    if not _int(obj["hz"], 1, 240) or not _int(obj["seed"], 0, 2**63 - 1) or not _hex_digest(obj["head"]):
        raise ReplayError("invalid checkpoint authority")
    raw = obj["frames"]
    if type(raw) is not list or len(raw) > MAX_EVENTS:
        raise ReplayError("invalid frame budget")
    frames = []
    for item in raw:
        if type(item) is not dict or set(item) != {"tick", "prior", "digest", "events"}:
            raise ReplayError("invalid frame schema")
        if not _int(item["tick"], 1, 10_000_000) or not _hex_digest(item["prior"]) or not _hex_digest(item["digest"]):
            raise ReplayError("invalid frame identity")
        events = item["events"]
        if type(events) is not list or len(events) > 32:
            raise ReplayError("invalid event budget")
        decoded = []
        for event in events:
            if type(event) is not dict or set(event) != {"tick", "action", "pressed"}:
                raise ReplayError("invalid event schema")
            decoded.append(InputEvent(event["tick"], event["action"], event["pressed"]))
        frames.append(ReplayFrame(item["tick"], tuple(decoded), item["prior"], item["digest"]))
    replay = FixedTickReplay.verify(hz=obj["hz"], seed=obj["seed"], frames=tuple(frames))
    if replay.digest != obj["head"]:
        raise ReplayError("checkpoint head divergence")
    return replay
