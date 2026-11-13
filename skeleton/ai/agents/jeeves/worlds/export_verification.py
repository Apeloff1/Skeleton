"""Source-bound verification of a standalone Jeeves HTML game export.

This verifier does not approve world source or establish device playability.
It rejects an artifact that differs by even one byte from the deterministic
compiler output at the requested canonical source revision.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
import stat

from skeleton.jeeves.worlds.world_canon import (
    CanonError, WorldStore, _id, compile_html, prove,
)

MAX_EXPORT_BYTES = 3 * 524288


def verify_export(store: WorldStore, world_id: str, expected_digest: str) -> dict[str, str]:
    """Verify source lease, bounded artifact custody and exact compiler output."""
    _id(world_id, "world_id")
    if type(expected_digest) is not str or len(expected_digest) != 64 or any(
        ch not in "0123456789abcdef" for ch in expected_digest
    ):
        raise CanonError("invalid_source_digest")
    source = store.read(world_id)
    actual_digest = prove(source).source_digest
    if actual_digest != expected_digest:
        raise CanonError("stale_source")
    expected = compile_html(source).encode("utf-8")
    if len(expected) > MAX_EXPORT_BYTES:
        raise CanonError("output_too_large")
    directory = store._directory()
    try:
        name = world_id + ".html"
        try:
            handle = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                             dir_fd=directory)
        except FileNotFoundError:
            raise CanonError("export_not_found") from None
        try:
            before = os.fstat(handle)
            if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                    or before.st_size > MAX_EXPORT_BYTES):
                raise CanonError("unsafe_export")
            with os.fdopen(os.dup(handle), "rb") as stream:
                actual = stream.read(MAX_EXPORT_BYTES + 1)
            after = os.fstat(handle)
            entry = os.stat(name, dir_fd=directory, follow_symlinks=False)
            if (len(actual) > MAX_EXPORT_BYTES or
                    (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns,
                     before.st_ctime_ns) !=
                    (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns,
                     after.st_ctime_ns) or
                    (after.st_dev, after.st_ino) != (entry.st_dev, entry.st_ino)):
                raise CanonError("export_changed_during_read")
        finally:
            os.close(handle)
        # Source is re-read after the artifact, detecting intervening revisions.
        if prove(store.read(world_id)).source_digest != expected_digest:
            raise CanonError("stale_source")
        if actual != expected:
            raise CanonError("export_mismatch")
        return {"schema": "jeeves.world.export_verification.v1",
                "world_id": world_id, "source_digest": expected_digest,
                "html_sha256": sha256(actual).hexdigest(), "status": "verified"}
    finally:
        os.close(directory)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a source-bound Jeeves HTML export")
    parser.add_argument("workspace")
    parser.add_argument("world_id")
    parser.add_argument("source_digest")
    args = parser.parse_args()
    try:
        receipt = verify_export(WorldStore(args.workspace), args.world_id,
                                args.source_digest)
    except (CanonError, OSError) as exc:
        parser.exit(2, f"export verification failed: {exc}\n")
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
