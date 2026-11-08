"""Read-only, source-bound playable world handoff for an approved canonical world.

This CLI never creates or changes a world. The operator supplies the exact
approved digest, which is rechecked before any artifact bytes are emitted.
The JSON envelope is intentionally portable across desktop and builder tools.
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
from hashlib import sha256
from typing import Sequence

from skeleton.jeeves.worlds.world_canon import (
    CanonError, MAX_SOURCE_BYTES, WorldStore, canonical, compile_html,
    compile_manifest, digest,
)

HANDOFF_SCHEMA = "jeeves.world.handoff.v1"
MAX_HTML_BYTES = MAX_SOURCE_BYTES * 4
MAX_ENVELOPE_BYTES = MAX_HTML_BYTES * 2


def build_handoff(world: dict, approved_digest: str) -> dict:
    """Create a reproducible, content-addressed handoff without side effects."""
    if type(approved_digest) is not str or len(approved_digest) != 64 or any(
        ch not in "0123456789abcdef" for ch in approved_digest
    ):
        raise CanonError("invalid_approval_digest")
    actual = digest(world)
    if actual != approved_digest:
        raise CanonError("stale_source")
    manifest = compile_manifest(world)
    if manifest["proof"]["source_digest"] != actual:
        raise CanonError("proof_source_mismatch")
    html = compile_html(world).encode("utf-8")
    if len(html) > MAX_HTML_BYTES:
        raise CanonError("handoff_too_large")
    return {
        "schema": HANDOFF_SCHEMA,
        "world_id": world["id"],
        "source_digest": actual,
        "manifest": manifest,
        "html_sha256": sha256(html).hexdigest(),
        "html_bytes": len(html),
        "html_base64": base64.b64encode(html).decode("ascii"),
    }


def verify_handoff(raw: bytes) -> dict:
    """Validate a portable handoff without trusting its claimed hash or proof."""
    from skeleton.jeeves.worlds.world_canon import strict_json
    if type(raw) is not bytes or len(raw) > MAX_ENVELOPE_BYTES:
        raise CanonError("handoff_too_large")
    envelope = strict_json(raw)
    if type(envelope) is not dict or set(envelope) != {
        "schema", "world_id", "source_digest", "manifest",
        "html_sha256", "html_bytes", "html_base64",
    } or envelope["schema"] != HANDOFF_SCHEMA:
        raise CanonError("invalid_handoff")
    if type(envelope["html_base64"]) is not str:
        raise CanonError("invalid_handoff")
    try:
        html = base64.b64decode(envelope["html_base64"], validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise CanonError("invalid_handoff_encoding") from exc
    if len(html) > MAX_HTML_BYTES:
        raise CanonError("handoff_too_large")
    manifest = envelope["manifest"]
    if type(manifest) is not dict or set(manifest) != {"schema", "world", "proof"}:
        raise CanonError("invalid_handoff")
    world = manifest["world"]
    expected = build_handoff(world, envelope["source_digest"])
    if canonical(expected) != canonical(envelope):
        raise CanonError("handoff_integrity_mismatch")
    return {"schema": HANDOFF_SCHEMA, "world_id": world["id"],
            "source_digest": expected["source_digest"],
            "html_sha256": expected["html_sha256"], "html_bytes": len(html)}


def run(argv: Sequence[str] | None = None, *, output_stream=None,
        error_stream=None, input_stream=None) -> int:
    parser = argparse.ArgumentParser(description="Approved world to offline playable handoff")
    parser.add_argument("--root", help="Existing canonical world store")
    parser.add_argument("--world-id", help="Approved world ID")
    parser.add_argument("--approved-digest", help="Exact reviewed canonical digest")
    parser.add_argument("action", choices=("build", "verify"))
    args = parser.parse_args(argv)
    out = output_stream if output_stream is not None else sys.stdout.buffer
    err = error_stream if error_stream is not None else sys.stderr
    incoming = input_stream if input_stream is not None else sys.stdin.buffer
    try:
        if args.action == "build":
            if not args.root or not args.world_id or not args.approved_digest:
                raise CanonError("approval_required")
            source = WorldStore(args.root).read(args.world_id)
            payload = canonical(build_handoff(source, args.approved_digest))
        else:
            raw = incoming.read(MAX_ENVELOPE_BYTES + 1)
            if type(raw) is not bytes:
                raise CanonError("invalid_handoff")
            payload = canonical(verify_handoff(raw))
        if len(payload) > MAX_ENVELOPE_BYTES:
            raise CanonError("handoff_too_large")
        out.write(payload + b"\n")
        return 0
    except (CanonError, OSError, ValueError, TypeError) as exc:
        code = exc.code if isinstance(exc, CanonError) else "handoff_io_error"
        err.write(json.dumps({"error": code}, separators=(",", ":")) + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(run())
