"""Bounded, principal/source-fenced local GGUF JSONL publication.

The caller must already hold an operator-approved installed-source fence.
This module neither installs weights nor grants inference/rights/device access.
It must not log private prompts, records, paths or native exception text.
"""
from __future__ import annotations

import json
from typing import Any, TextIO


class NativePublicationHold(ValueError):
    """No successful native response was completely published."""


def emit_native_jsonl(
    worker: object,
    source_fence: Any,
    record: dict[str, object],
    destination: TextIO,
    *,
    maximum_result_bytes: int = 4 * 1024 * 1024,
) -> int:
    """Publish one bounded JSONL record only against a live installed source.

    Checks installed model rights/epoch before and after encoding, checks the
    final UTF-8 disclosure ceiling before writing, then verifies a complete
    text write, flush and post-write source identity. A failed or partial
    write is an unknown disclosure effect; callers must never auto-retry it.
    """
    if (type(maximum_result_bytes) is not int
            or not 1 <= maximum_result_bytes <= 16 * 1024 * 1024):
        raise NativePublicationHold("invalid native output byte ceiling")
    if type(record) is not dict:
        raise NativePublicationHold("native record requires a typed object")
    inspect = getattr(source_fence, "assert_live", None)
    if not callable(inspect):
        raise NativePublicationHold("installed native source custody required")
    write = getattr(destination, "write", None)
    if not callable(write):
        raise NativePublicationHold("bounded text stream required")
    inspect(worker)
    try:
        serialized = json.dumps(
            record, sort_keys=True, ensure_ascii=False,
            allow_nan=False, separators=(",", ":"),
        ) + "\n"
        result_bytes = len(serialized.encode("utf-8", "strict"))
    except (TypeError, ValueError, UnicodeError, OverflowError) as exc:
        raise NativePublicationHold("native output JSON contract invalid") from exc
    if result_bytes > maximum_result_bytes:
        raise NativePublicationHold("native output exceeds byte ceiling")
    inspect(worker)
    count = write(serialized)
    if type(count) is not int or count != len(serialized):
        raise NativePublicationHold("native output stream incomplete")
    flush = getattr(destination, "flush", None)
    if callable(flush):
        flush()
    inspect(worker)
    return result_bytes


__all__ = ["NativePublicationHold", "emit_native_jsonl"]
