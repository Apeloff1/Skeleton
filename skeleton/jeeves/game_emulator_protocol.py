"""Bounded data-only wire format shared by the native emulator host/worker."""

from __future__ import annotations

import hashlib
import json
import math
import struct
from collections.abc import Mapping
from typing import BinaryIO

SCHEMA = "skeleton.libretro_wire.v1"
MAX_METADATA = 65536
MAX_PACKET = 96 * 1024 * 1024
MAX_BINARY = 64 * 1024 * 1024


class EmulatorProtocolError(ValueError):
    pass


def _pairs(values: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in values:
        if key in result:
            raise EmulatorProtocolError("duplicate protocol field")
        result[key] = value
    return result


def _constant(value: str) -> object:
    raise EmulatorProtocolError("nonfinite protocol constant: " + value)


def _shape(
    value: object, depth: int = 0, counter: list[int] | None = None, budget: list[int] | None = None
) -> None:
    if counter is None:
        counter = [0]
    if budget is None:
        budget = [MAX_METADATA]
    counter[0] += 1
    budget[0] -= 4
    if depth > 16 or counter[0] > 8192:
        raise EmulatorProtocolError("protocol structural capacity exceeded")
    if isinstance(value, dict):
        if len(value) > 256:
            raise EmulatorProtocolError("protocol object capacity exceeded")
        for key, item in value.items():
            if not isinstance(key, str) or len(key) > 256:
                raise EmulatorProtocolError("invalid protocol field identity")
            budget[0] -= len(key) + 3
            _shape(item, depth + 1, counter, budget)
    elif isinstance(value, list):
        if len(value) > 512:
            raise EmulatorProtocolError("protocol sequence capacity exceeded")
        for item in value:
            _shape(item, depth + 1, counter, budget)
    elif isinstance(value, str):
        if len(value) > MAX_METADATA:
            raise EmulatorProtocolError("protocol string capacity exceeded")
        budget[0] -= len(json.dumps(value, ensure_ascii=True))
    elif type(value) is float and not math.isfinite(value):
        raise EmulatorProtocolError("protocol numeric value is not finite")
    elif type(value) is int and abs(value) > 2**64:
        raise EmulatorProtocolError("protocol integer capacity exceeded")
    elif value is not None and type(value) not in (str, bool, int, float):
        raise EmulatorProtocolError("protocol contains a non-JSON value")
    if budget[0] < 0:
        raise EmulatorProtocolError("protocol aggregate string capacity exceeded")


def _write(stream: BinaryIO, data: bytes | memoryview) -> None:
    view = memoryview(data)
    cursor = 0
    while cursor < len(view):
        count = stream.write(view[cursor:])
        if count is None or count <= 0:
            raise OSError("native worker transport write stopped")
        cursor += count


def _read(stream: BinaryIO, size: int) -> bytes:
    result = bytearray()
    while len(result) < size:
        chunk = stream.read(min(size - len(result), 1024 * 1024))
        if not chunk:
            raise EOFError("native worker transport closed")
        result.extend(chunk)
    return bytes(result)


def write_packet(
    stream: BinaryIO, message: Mapping[str, object], blocks: Mapping[str, bytes] | None = None
) -> None:
    blobs = blocks or {}
    if len(blobs) > 8 or any(
        not isinstance(name, str)
        or not name
        or len(name) > 64
        or not isinstance(data, bytes)
        or len(data) > MAX_BINARY
        for name, data in blobs.items()
    ):
        raise EmulatorProtocolError("invalid binary block capacity or identity")
    metadata = {
        "schema_version": SCHEMA,
        "message": dict(message),
        "blocks": [
            {"name": name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            for name, data in blobs.items()
        ],
    }
    _shape(metadata)
    raw = json.dumps(metadata, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if len(raw) > MAX_METADATA or sum(len(data) for data in blobs.values()) + len(raw) > MAX_PACKET:
        raise EmulatorProtocolError("native IPC capacity exceeded")
    _write(stream, struct.pack(">I", len(raw)))
    _write(stream, raw)
    for data in blobs.values():
        view = memoryview(data)
        for start in range(0, len(data), 1024 * 1024):
            _write(stream, view[start : start + 1024 * 1024])
    stream.flush()


def read_packet(stream: BinaryIO) -> tuple[dict[str, object], dict[str, bytes]]:
    size = struct.unpack(">I", _read(stream, 4))[0]
    if not 1 <= size <= MAX_METADATA:
        raise EmulatorProtocolError("invalid native metadata length")
    raw = _read(stream, size)
    try:
        metadata = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise EmulatorProtocolError("invalid native metadata JSON") from exc
    _shape(metadata)
    if (
        not isinstance(metadata, dict)
        or set(metadata) != {"schema_version", "message", "blocks"}
        or metadata["schema_version"] != SCHEMA
        or not isinstance(metadata["message"], dict)
        or not isinstance(metadata["blocks"], list)
        or len(metadata["blocks"]) > 8
    ):
        raise EmulatorProtocolError("native wire schema differs")
    declared = metadata["blocks"]
    total = size
    names = set()
    for item in declared:
        if (
            not isinstance(item, dict)
            or set(item) != {"name", "size", "sha256"}
            or not isinstance(item["name"], str)
            or not 1 <= len(item["name"]) <= 64
            or item["name"] in names
            or type(item["size"]) is not int
            or not 0 <= item["size"] <= MAX_BINARY
            or not isinstance(item["sha256"], str)
            or len(item["sha256"]) != 64
            or any(c not in "0123456789abcdef" for c in item["sha256"])
        ):
            raise EmulatorProtocolError("native binary manifest is invalid")
        names.add(item["name"])
        total += item["size"]
        if total > MAX_PACKET:
            raise EmulatorProtocolError("native binary aggregate capacity exceeded")
    blocks = {}
    for item in declared:
        data = _read(stream, item["size"])
        if hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise EmulatorProtocolError("native binary checksum differs")
        blocks[item["name"]] = data
    return metadata["message"], blocks
