"""Strict, byte-bounded portable checkpoint codec for fixed-tick replay.

This is an in-memory codec only, not durable filesystem publication or a
first-install / device / production certification mechanism.
"""
from __future__ import annotations

import json

from skeleton.simulation.fixed_tick import (
    FixedTickReplay, InputEvent, ReplayError, ReplayFrame, MAX_EVENTS,
)

SCHEMA = "skeleton.game.replay-checkpoint.v1"
MAX_CHECKPOINT_BYTES = 8_000_000
_HEX = frozenset("0123456789abcdef")


def _hex_digest(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(c in _HEX for c in value)


def _int(value: object, low: int, high: int) -> bool:
    return type(value) is int and low <= value <= high


def _unique_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Reject conflicting duplicate keys at *every* JSON object depth."""
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ReplayError("duplicate checkpoint JSON key")
        result[key] = value
    return result


def _reject_nonfinite(_token: str) -> object:
    raise ReplayError("non-finite checkpoint JSON constant")


def _append_bounded(buffer: bytearray, piece: bytes) -> None:
    if len(piece) > MAX_CHECKPOINT_BYTES - len(buffer):
        raise ReplayError("checkpoint byte budget exhausted")
    buffer.extend(piece)


def encode(replay: FixedTickReplay) -> bytes:
    """Stream individual canonical frames into a capped output buffer.

    Do not first build one huge frames-of-events list only to discover that
    it is larger than the checkpoint envelope. Source history is replay-
    verified before serializing: an object with forged frame/head fields
    cannot mint an authoritative-looking checkpoint.
    """
    if not isinstance(replay, FixedTickReplay):
        raise ReplayError("checkpoint requires canonical replay")
    frames = replay.frames
    if len(frames) > MAX_EVENTS:
        raise ReplayError("checkpoint frame count exceeds bound")
    verified = FixedTickReplay.verify(
        hz=replay.hz, seed=replay.seed, frames=frames,
    )
    if verified.digest != replay.digest or verified.tick != replay.tick:
        raise ReplayError("checkpoint source replay divergence")

    output = bytearray()
    _append_bounded(output, b'{"frames":[')
    for index, frame in enumerate(frames):
        if index:
            _append_bounded(output, b",")
        record = {
            "tick": frame.tick,
            "prior": frame.prior_digest,
            "digest": frame.digest,
            "events": [
                {"tick": event.tick, "action": event.action, "pressed": event.pressed}
                for event in frame.events
            ],
        }
        try:
            encoded = json.dumps(
                record, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            ).encode("ascii")
        except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
            raise ReplayError("invalid checkpoint frame encoding") from exc
        _append_bounded(output, encoded)

    # The canonical top-level key ordering is frames/head/hz/schema/seed.
    # Removing only the leading "{" of the remaining sorted keys produces
    # exactly the bytes of a monolithic sort_keys=True JSON dump.
    tail = json.dumps({
        "head": replay.digest,
        "hz": replay.hz,
        "schema": SCHEMA,
        "seed": replay.seed,
    }, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    _append_bounded(output, b"]," + tail[1:])
    return bytes(output)


def decode(data: bytes) -> FixedTickReplay:
    """Accept only unique-key, strict, bounded and independently replayed data."""
    if type(data) is not bytes or len(data) > MAX_CHECKPOINT_BYTES:
        raise ReplayError("checkpoint must be bounded bytes")
    try:
        obj = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_unique_keys,
            parse_constant=_reject_nonfinite,
        )
    except ReplayError:
        raise
    except (UnicodeError, ValueError, TypeError, RecursionError) as exc:
        raise ReplayError("invalid checkpoint encoding") from exc
    if (type(obj) is not dict
            or set(obj) != {"schema", "hz", "seed", "head", "frames"}
            or obj["schema"] != SCHEMA):
        raise ReplayError("invalid checkpoint schema")
    if (not _int(obj["hz"], 1, 240)
            or not _int(obj["seed"], 0, 2**63 - 1)
            or not _hex_digest(obj["head"])):
        raise ReplayError("invalid checkpoint authority")
    raw = obj["frames"]
    if type(raw) is not list or len(raw) > MAX_EVENTS:
        raise ReplayError("invalid frame budget")
    frames = []
    for item in raw:
        if type(item) is not dict or set(item) != {"tick", "prior", "digest", "events"}:
            raise ReplayError("invalid frame schema")
        if (not _int(item["tick"], 1, 10_000_000)
                or not _hex_digest(item["prior"])
                or not _hex_digest(item["digest"])):
            raise ReplayError("invalid frame identity")
        events = item["events"]
        if type(events) is not list or len(events) > 32:
            raise ReplayError("invalid event budget")
        decoded = []
        for event in events:
            if type(event) is not dict or set(event) != {"tick", "action", "pressed"}:
                raise ReplayError("invalid event schema")
            decoded.append(
                InputEvent(event["tick"], event["action"], event["pressed"]),
            )
        frames.append(
            ReplayFrame(item["tick"], tuple(decoded), item["prior"], item["digest"]),
        )
    replay = FixedTickReplay.verify(
        hz=obj["hz"], seed=obj["seed"], frames=tuple(frames),
    )
    if replay.digest != obj["head"]:
        raise ReplayError("checkpoint head divergence")
    return replay
