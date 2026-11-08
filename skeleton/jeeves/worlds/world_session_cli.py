"""Offline operator CLI for approved canonical-world session replay.

Reads only a previously published WorldStore world, never changes custody.
Receipts are bounded before parsing and are written to stdout only after full
source-bound validation. No shell, network, model, or filesystem export needed.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from skeleton.jeeves.worlds.world_canon import CanonError, WorldStore, canonical
from skeleton.jeeves.worlds.world_session import (
    MAX_RECEIPT_BYTES, export_json, restore_json,
)

MAX_INPUT_BYTES = 65536


def _read_bounded(stream: object) -> bytes:
    data = stream.read(MAX_INPUT_BYTES + 1)
    if type(data) is not bytes:
        raise CanonError("invalid_session_payload")
    if len(data) > MAX_INPUT_BYTES:
        raise CanonError("session_too_large")
    return data


def _choice_ids(raw: bytes) -> list[str]:
    from skeleton.jeeves.worlds.world_canon import strict_json
    obj = strict_json(raw)
    if type(obj) is not list:
        raise CanonError("invalid_session_trace")
    return obj


def run(argv: Sequence[str] | None = None, *, input_stream=None,
        output_stream=None, error_stream=None) -> int:
    parser = argparse.ArgumentParser(description="Offline reviewed-world session custody")
    parser.add_argument("--root", required=True, help="Existing canonical world directory")
    parser.add_argument("--world-id", required=True, help="Published canonical world identifier")
    parser.add_argument("action", choices=("export", "restore"))
    args = parser.parse_args(argv)
    source_in = input_stream if input_stream is not None else sys.stdin.buffer
    sink = output_stream if output_stream is not None else sys.stdout.buffer
    errors = error_stream if error_stream is not None else sys.stderr
    try:
        world = WorldStore(args.root).read(args.world_id)
        raw = _read_bounded(source_in)
        if args.action == "export":
            payload = export_json(world, _choice_ids(raw))
        else:
            payload = canonical(restore_json(world, raw))
        if len(payload) > MAX_RECEIPT_BYTES:
            raise CanonError("session_too_large")
        sink.write(payload + b"\n")
        return 0
    except (CanonError, OSError) as exc:
        code = exc.code if isinstance(exc, CanonError) else "session_io_error"
        errors.write(json.dumps({"error": code}, separators=(",", ":")) + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(run())
