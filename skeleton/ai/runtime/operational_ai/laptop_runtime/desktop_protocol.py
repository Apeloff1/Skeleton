"""Strict bounded binary stdio frames for a single local Jeeves GGUF worker.

This is an IPC framing contract, not a second model, database or authorization
layer. No prompts, installed paths or exceptions are written to logs.
"""
from __future__ import annotations

import json
import math
from typing import BinaryIO

SCHEMA_COMMAND = "jeeves.desktop.command.v1"
SCHEMA_RESPONSE = "jeeves.desktop.response.v1"
MAX_INBOUND = 65536
MAX_OUTBOUND = 262144
MAX_PROMPT = 32768
MAX_HISTORY = 128
MAX_FRAME_DEPTH = 96
MAX_FRAME_NODES = 65536


class DesktopProtocolHold(ValueError):
    """A frame or request violated the private local transport contract."""


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise DesktopProtocolHold("duplicate framed JSON object key")
        result[key] = value
    return result


def _bad_constant(_: str) -> None:
    raise DesktopProtocolHold("nonfinite framed JSON denied")


def _finite_float(token: str) -> float:
    result = float(token)
    if not math.isfinite(result):
        raise DesktopProtocolHold("nonfinite framed JSON number denied")
    return result


def _validate_frame_tree(value: object) -> None:
    """Bound nesting, aggregate nodes and Unicode after strict UTF-8 decode.

    JSON decoders can generate lone surrogate code points from escape
    sequences even when the input is valid UTF-8. Such strings cannot be
    safely published to SQLite, the GUI or a sibling IPC frame.
    """
    queue: list[tuple[object, int]] = [(value, 0)]
    nodes = 0
    while queue:
        current, depth = queue.pop()
        nodes += 1
        if depth > MAX_FRAME_DEPTH or nodes > MAX_FRAME_NODES:
            raise DesktopProtocolHold("private frame exceeds structural budget")
        if isinstance(current, str):
            if any(0xD800 <= ord(character) <= 0xDFFF for character in current):
                raise DesktopProtocolHold("private frame contains invalid Unicode")
        elif type(current) is float:
            if not math.isfinite(current):
                raise DesktopProtocolHold("nonfinite private frame value")
        elif isinstance(current, list):
            if nodes + len(queue) + len(current) > MAX_FRAME_NODES:
                raise DesktopProtocolHold("private frame exceeds structural budget")
            queue.extend((item, depth + 1) for item in current)
        elif isinstance(current, dict):
            if nodes + len(queue) + 2 * len(current) > MAX_FRAME_NODES:
                raise DesktopProtocolHold("private frame exceeds structural budget")
            for key, item in current.items():
                queue.append((key, depth + 1))
                queue.append((item, depth + 1))


def encoded(value: object, *, limit: int) -> bytes:
    if type(limit) is not int or not 16 <= limit <= MAX_OUTBOUND:
        raise DesktopProtocolHold("invalid transport frame ceiling")
    try:
        payload = json.dumps(
            value, sort_keys=True, ensure_ascii=False, allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8", "strict")
    except (TypeError, ValueError, UnicodeError, OverflowError, RecursionError) as exc:
        raise DesktopProtocolHold("unserializable private frame") from exc
    if not 2 <= len(payload) <= limit:
        raise DesktopProtocolHold("private frame outside byte ceiling")
    return len(payload).to_bytes(4, "big") + payload


def decoded(payload: bytes, *, limit: int) -> object:
    if type(payload) is not bytes or not 2 <= len(payload) <= limit:
        raise DesktopProtocolHold("frame payload outside declared byte ceiling")
    try:
        value = json.loads(
            payload.decode("utf-8", "strict"), object_pairs_hook=_unique,
            parse_constant=_bad_constant, parse_float=_finite_float,
        )
        _validate_frame_tree(value)
        return value
    except (ValueError, UnicodeError, TypeError, OverflowError, RecursionError) as exc:
        raise DesktopProtocolHold("invalid strict private JSON frame") from exc


def _read_exact(source: BinaryIO, count: int, *, allow_initial_eof: bool) -> bytes | None:
    if count <= 0 or count > MAX_OUTBOUND:
        raise DesktopProtocolHold("invalid bounded frame read")
    result = bytearray()
    while len(result) < count:
        part = source.read(count - len(result))
        if type(part) is not bytes:
            raise DesktopProtocolHold("framed input must be binary")
        if not part:
            if not result and allow_initial_eof:
                return None
            raise DesktopProtocolHold("truncated private frame")
        result.extend(part)
    return bytes(result)


def read_frame(source: BinaryIO, *, limit: int = MAX_INBOUND) -> object | None:
    """EOF between frames means disconnect; EOF mid-frame is an error."""
    if type(limit) is not int or not 16 <= limit <= MAX_OUTBOUND:
        raise DesktopProtocolHold("invalid incoming frame ceiling")
    header = _read_exact(source, 4, allow_initial_eof=True)
    if header is None:
        return None
    size = int.from_bytes(header, "big")
    if not 2 <= size <= limit:
        raise DesktopProtocolHold("malformed or oversized private frame")
    payload = _read_exact(source, size, allow_initial_eof=False)
    assert payload is not None
    return decoded(payload, limit=limit)


def write_frame(
    target: BinaryIO, value: object, *, limit: int = MAX_OUTBOUND,
    source_check=None,
) -> int:
    """One publication attempt. A short write is terminal, never replayed."""
    if source_check is not None:
        source_check()
    raw = encoded(value, limit=limit)
    if source_check is not None:
        source_check()
    # Buffered binary pipes ordinarily accept the complete finite frame.
    # Never silently write another copy after a partial private disclosure.
    count = target.write(raw)
    if type(count) is not int or count != len(raw):
        raise DesktopProtocolHold("incomplete private binary frame publication")
    flush = getattr(target, "flush", None)
    if callable(flush):
        flush()
    if source_check is not None:
        source_check()
    return len(raw)


_ALLOWED: dict[str, tuple[frozenset[str], frozenset[str]]] = {
    "status": (frozenset(), frozenset()),
    "telemetry": (frozenset(), frozenset()),
    "source-status": (frozenset(), frozenset()),
    "agent": (
        frozenset({"run_id", "prompt"}),
        frozenset({"maximum_steps", "maximum_model_calls", "maximum_wall_seconds", "profile"}),
    ),
    "durable": (
        frozenset({"run_id", "prompt", "action"}),
        frozenset({"maximum_steps", "maximum_model_calls", "maximum_wall_seconds"}),
    ),
    "new": (frozenset(), frozenset()),
    "resume": (frozenset({"session_id"}), frozenset()),
    "turn": (frozenset({"request_id", "prompt"}), frozenset({"seed", "temperature", "context"})),
    "history": (frozenset(), frozenset()),
    "close": (frozenset(), frozenset()),
    "quit": (frozenset(), frozenset()),
}


def command(op: str, **fields: object) -> dict[str, object]:
    """Pure, source-independent input validation before private operations."""
    from .contracts import identifier, number, nonnegative, utf8

    if type(op) is not str or op not in _ALLOWED:
        raise DesktopProtocolHold("unknown desktop operation")
    required, optional = _ALLOWED[op]
    if set(fields) - (required | optional) or not required <= set(fields):
        raise DesktopProtocolHold("missing or unexpected desktop operation fields")
    result: dict[str, object] = {"schema": SCHEMA_COMMAND, "op": op}
    if "session_id" in fields:
        result["session_id"] = identifier(fields["session_id"], "session ID")
    if "run_id" in fields:
        result["run_id"] = identifier(fields["run_id"], "native agent run ID")
    if "profile" in fields:
        if type(fields["profile"]) is not str or fields["profile"] not in (
            "guarded", "advanced",
        ):
            raise DesktopProtocolHold("unapproved native planning profile")
        result["profile"] = fields["profile"]
    if "action" in fields:
        if (
            type(fields["action"]) is not str
            or fields["action"] not in ("start", "inspect", "resume", "replay")
        ):
            raise DesktopProtocolHold("invalid explicit durable action")
        result["action"] = fields["action"]
    if "request_id" in fields:
        result["request_id"] = identifier(fields["request_id"], "request ID")
    if "prompt" in fields:
        result["prompt"] = utf8(fields["prompt"], maximum=MAX_PROMPT)
    if "seed" in fields:
        result["seed"] = nonnegative(fields["seed"], maximum=2**32 - 1)
    if "temperature" in fields:
        result["temperature"] = number(
            fields["temperature"], minimum=0.000000001, maximum=2,
        )
    if "context" in fields:
        if type(fields["context"]) is not bool:
            raise DesktopProtocolHold("conversation context must be explicitly boolean")
        result["context"] = fields["context"]
    for key, ceiling in (
        ("maximum_steps", 64),
        ("maximum_model_calls", 64),
        ("maximum_wall_seconds", 600),
    ):
        if key in fields:
            value = nonnegative(fields[key], maximum=ceiling)
            if value < 1:
                raise DesktopProtocolHold("native agent budget must be positive")
            result[key] = value
    encoded(result, limit=MAX_INBOUND)
    return result


def require_command(value: object) -> dict[str, object]:
    if type(value) is not dict or set(value) - (
        {"schema", "op", "session_id", "request_id", "prompt", "seed", "temperature",
         "context", "run_id", "maximum_steps", "maximum_model_calls",
         "maximum_wall_seconds", "action", "profile"}
    ):
        raise DesktopProtocolHold("desktop command envelope has unknown fields")
    if value.get("schema") != SCHEMA_COMMAND:
        raise DesktopProtocolHold("unsupported desktop command schema")
    op = value.get("op")
    if type(op) is not str:
        raise DesktopProtocolHold("missing desktop operation")
    validated = command(op, **{k: v for k, v in value.items() if k not in ("schema", "op")})
    if validated != value:
        raise DesktopProtocolHold("desktop command normalization mismatch")
    return validated


def response(status: str, **fields: object) -> dict[str, object]:
    if type(status) is not str or not status.isascii() or not 1 <= len(status) <= 64:
        raise DesktopProtocolHold("invalid desktop response status")
    item = {"schema": SCHEMA_RESPONSE, "status": status, "release_certified": False}
    item.update(fields)
    if item.get("schema") != SCHEMA_RESPONSE or item.get("release_certified") is not False:
        raise DesktopProtocolHold("unapproved desktop response override")
    encoded(item, limit=MAX_OUTBOUND)
    return item
