"""Strict, byte-bounded portable checkpoint codec for fixed-tick replay.

This is an in-memory codec only, not durable filesystem publication or a
first-install / device / production certification mechanism.
"""
from __future__ import annotations

import json

from skeleton.simulation.fixed_tick import (
    FixedTickReplay, InputEvent, ReplayError, ReplayFrame, MAX_EVENTS, MAX_TICKS,
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


def _parse_integer(token: str) -> int:
    # All integer fields are nonnegative and at most signed 64-bit.
    if not 1 <= len(token) <= 19 or token.startswith("-"):
        raise ReplayError("checkpoint integer exceeds bound")
    value = int(token)
    if value > 2**63 - 1:
        raise ReplayError("checkpoint integer exceeds bound")
    return value


def _reject_float(_token: str) -> object:
    raise ReplayError("floating-point checkpoint field")


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
    if type(replay) is not FixedTickReplay:
        raise ReplayError("checkpoint requires canonical replay")
    hz, seed, tick, head = replay.hz, replay.seed, replay.tick, replay.digest
    if not _int(tick, 0, MAX_TICKS) or not _hex_digest(head):
        raise ReplayError("invalid checkpoint source identity")
    if type(replay._frames) is not list or len(replay._frames) > MAX_EVENTS:
        raise ReplayError("checkpoint frame count exceeds bound")
    frames = replay.frames
    verified = FixedTickReplay(hz=hz, seed=seed)
    output = bytearray()
    _append_bounded(output, b'{"frames":[')
    for index, supplied in enumerate(frames):
        if type(supplied) is not ReplayFrame:
            raise ReplayError("invalid checkpoint source frame")
        if (not _int(supplied.tick, 1, MAX_TICKS)
                or not _hex_digest(supplied.prior_digest)
                or not _hex_digest(supplied.digest)):
            raise ReplayError("invalid checkpoint source frame identity")
        frame = verified.advance(supplied.events)
        if (frame.tick != supplied.tick or frame.prior_digest != supplied.prior_digest
                or frame.digest != supplied.digest):
            raise ReplayError("checkpoint source replay divergence")
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

    if verified.digest != head or verified.tick != tick:
        raise ReplayError("checkpoint source replay divergence")
    if (replay.digest != head or replay.tick != tick
            or replay.hz != hz or replay.seed != seed or len(replay._frames) != len(frames)):
        raise ReplayError("checkpoint source changed during encoding")

    # The canonical top-level key ordering is frames/head/hz/schema/seed.
    # Removing only the leading "{" of the remaining sorted keys produces
    # exactly the bytes of a monolithic sort_keys=True JSON dump.
    tail = json.dumps({
        "head": head,
        "hz": hz,
        "schema": SCHEMA,
        "seed": seed,
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
            parse_int=_parse_integer,
            parse_float=_reject_float,
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
        if (not _int(item["tick"], 1, MAX_TICKS)
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
