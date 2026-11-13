"""Offline operator journey: preview a typed edit, then explicitly publish and hand off.

No implicit approvals. The preview is read-only and its source/candidate
digests must be carried by the operator into a separate publish invocation.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from skeleton.jeeves.worlds.world_canon import CanonError, MAX_SOURCE_BYTES, canonical, strict_json
from skeleton.jeeves.worlds.world_reviewed_delivery import preview, publish_approved

MAX_OPERATION_BYTES = 65536


def run(argv: Sequence[str] | None = None, *, input_stream=None,
        output_stream=None, error_stream=None) -> int:
    parser = argparse.ArgumentParser(description="Offline reviewed world delivery")
    parser.add_argument("action", choices=("preview", "publish"))
    parser.add_argument("--root", required=True)
    parser.add_argument("--world-id", required=True)
    parser.add_argument("--expected-digest")
    parser.add_argument("--approved-digest")
    args = parser.parse_args(argv)
    incoming = input_stream if input_stream is not None else sys.stdin.buffer
    out = output_stream if output_stream is not None else sys.stdout.buffer
    err = error_stream if error_stream is not None else sys.stderr
    try:
        raw = incoming.read(MAX_OPERATION_BYTES + 1)
        if type(raw) is not bytes or len(raw) > MAX_OPERATION_BYTES:
            raise CanonError("operation_too_large")
        operation = strict_json(raw)
        if type(operation) is not dict:
            raise CanonError("invalid_operation")
        if args.action == "preview":
            if args.expected_digest is not None or args.approved_digest is not None:
                raise CanonError("approval_not_accepted_in_preview")
            result = preview(args.root, args.world_id, operation).as_dict()
        else:
            if not args.expected_digest or not args.approved_digest:
                raise CanonError("review_required")
            result = publish_approved(
                args.root, args.world_id, operation,
                expected_digest=args.expected_digest,
                approved_digest=args.approved_digest,
            )
        payload = canonical(result)
        if len(payload) > MAX_SOURCE_BYTES * 8:
            raise CanonError("delivery_too_large")
        out.write(payload + b"\n")
        return 0
    except (CanonError, OSError, ValueError, TypeError, OverflowError) as exc:
        code = exc.code if isinstance(exc, CanonError) else "delivery_io_error"
        err.write(json.dumps({"error": code}, separators=(",", ":")) + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(run())
