"""Operator-reviewed, source-leased canonical world edit CLI.

Preview is read-only. Commit requires both the exact current source digest and
an explicit candidate digest observed during preview. No implicit approval.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from skeleton.jeeves.worlds.world_canon import (
    CanonError, MAX_SOURCE_BYTES, WorldStore, canonical, digest, edit, prove,
    strict_json,
)

MAX_EDIT_BYTES = 65536


def _bounded(stream: object) -> bytes:
    raw = stream.read(MAX_EDIT_BYTES + 1)
    if type(raw) is not bytes:
        raise CanonError("invalid_edit_payload")
    if len(raw) > MAX_EDIT_BYTES:
        raise CanonError("edit_too_large")
    return raw


def run(argv: Sequence[str] | None = None, *, input_stream=None,
        output_stream=None, error_stream=None) -> int:
    parser = argparse.ArgumentParser(description="Reviewed canonical world edit")
    parser.add_argument("--root", required=True)
    parser.add_argument("--world-id", required=True)
    parser.add_argument("--expected-digest", help="Exact current published source digest")
    parser.add_argument("--reviewed-digest", help="Explicitly approved preview candidate digest")
    parser.add_argument("action", choices=("preview", "commit"))
    args = parser.parse_args(argv)
    incoming = input_stream if input_stream is not None else sys.stdin.buffer
    outgoing = output_stream if output_stream is not None else sys.stdout.buffer
    errors = error_stream if error_stream is not None else sys.stderr
    try:
        # Require authorization inputs before opening a world or reading an edit.
        if args.action == "commit" and (
            not args.expected_digest or not args.reviewed_digest
        ):
            raise CanonError("review_required")
        store = WorldStore(args.root)
        source = store.read(args.world_id)
        source_digest = digest(source)
        if args.expected_digest is not None and args.expected_digest != source_digest:
            raise CanonError("stale_source")
        operation = strict_json(_bounded(incoming))
        candidate = edit(source, operation)
        proof = prove(candidate)
        candidate_digest = proof.source_digest
        if args.action == "commit":
            if candidate_digest != args.reviewed_digest:
                raise CanonError("review_mismatch")
            # WorldStore.publish rechecks the lease under its exclusive lock.
            committed = store.publish(candidate, expected_digest=source_digest)
            result = {"action": "committed", "world_id": args.world_id,
                      "previous_digest": source_digest,
                      "candidate_digest": committed}
        else:
            result = {"action": "preview", "world_id": args.world_id,
                      "previous_digest": source_digest,
                      "candidate_digest": candidate_digest,
                      "proof": proof.as_dict(), "candidate": candidate}
        payload = canonical(result)
        if len(payload) > MAX_SOURCE_BYTES * 2:
            raise CanonError("output_too_large")
        outgoing.write(payload + b"\n")
        return 0
    except (CanonError, OSError) as exc:
        code = exc.code if isinstance(exc, CanonError) else "world_edit_io_error"
        errors.write(json.dumps({"error": code}, separators=(",", ":")) + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(run())
