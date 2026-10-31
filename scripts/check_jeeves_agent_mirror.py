#!/usr/bin/env python3
"""Fail closed when the two installed Jeeves agent source trees diverge.

All source reads are descriptor-anchored, bounded, and reject symlinks in
every ancestor, not merely symlinks visible in a prior path check.
"""

from __future__ import annotations

import argparse
from contextlib import ExitStack
import errno
import hashlib
import json
import os
from pathlib import Path
import stat

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = Path("skeleton/jeeves/agent")
MIRROR = Path("skeleton/ai/agents/jeeves/agent")
MAX_SOURCE_BYTES = 1_048_576
REQUIRED = (
    "adaptive_runtime.py",
    "adversarial_verifier_review.py",
    "code_delivery_quality.py",
    "code_scrutiny_loop.py",
    "delivery_assurance_milestones.py",
    "delivery_evidence_journal.py",
    "delivery_milestone_queue.py",
    "delivery_milestone_store.py",
    "delivery_milestone_driver.py",
    "delivery_milestone_workbench.py",
    "delivery_milestones.py",
    "final_delivery_reviews.py",
    "runtime.py",
    "working_context_cycle.py",
)


class SourceBlocked(Exception):
    """A source path cannot be read with the required custody guarantees."""

    def __init__(self, status: str) -> None:
        super().__init__(status)
        self.status = status


def _source_bytes(root: Path, relative: Path) -> bytes:
    """Walk from / using no-follow directory FDs, then read a regular file FD.

    A concurrent rename cannot redirect an already-open directory descriptor.
    O_NOFOLLOW rejects a file swapped to a symlink at the open boundary.
    No path-based check followed by an unguarded open is permitted.
    """
    if not all(hasattr(os, flag) for flag in ("O_NOFOLLOW", "O_DIRECTORY", "O_NONBLOCK")):
        raise SourceBlocked("unsafe")
    absolute = Path(os.path.abspath(root))
    if not absolute.is_absolute() or relative.is_absolute() or ".." in relative.parts:
        raise SourceBlocked("unsafe")
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    file_flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    try:
        with ExitStack() as stack:
            directory = os.open("/", directory_flags)
            stack.callback(os.close, directory)
            for component in (*absolute.parts[1:], *relative.parts[:-1]):
                child = os.open(component, directory_flags, dir_fd=directory)
                stack.callback(os.close, child)
                directory = child
            fd = os.open(relative.name, file_flags, dir_fd=directory)
            stack.callback(os.close, fd)
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_SOURCE_BYTES:
                raise SourceBlocked("unsafe")
            chunks = []
            total = 0
            while total <= MAX_SOURCE_BYTES:
                part = os.read(fd, min(65536, MAX_SOURCE_BYTES + 1 - total))
                if not part:
                    break
                chunks.append(part)
                total += len(part)
            after = os.fstat(fd)
            identity = lambda s: (
                s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns
            )
            if total > MAX_SOURCE_BYTES or total != before.st_size or identity(before) != identity(after):
                raise SourceBlocked("unsafe")
            return b"".join(chunks)
    except OSError as exc:
        if exc.errno == errno.ENOENT:
            raise SourceBlocked("missing") from exc
        if exc.errno in (errno.ELOOP, errno.ENOTDIR):
            raise SourceBlocked("symlink") from exc
        raise SourceBlocked("unsafe") from exc


def check_parity(root: Path = ROOT) -> dict[str, object]:
    """Compare bounded, descriptor-verified source bytes on both sides."""
    records: list[dict[str, object]] = []
    for name in REQUIRED:
        try:
            left = _source_bytes(root, CANONICAL / name)
            right = _source_bytes(root, MIRROR / name)
        except SourceBlocked as exc:
            records.append({"name": name, "status": exc.status})
            continue
        records.append({
            "name": name,
            "status": "matched" if left == right else "drifted",
            "canonical_sha256": hashlib.sha256(left).hexdigest(),
            "mirror_sha256": hashlib.sha256(right).hexdigest(),
            "canonical_bytes": len(left),
            "mirror_bytes": len(right),
        })
    return {
        "schema": "skeleton.jeeves.agent.mirror_parity.v1",
        "scope": "required code-delivery and milestone integration",
        "status": "passed" if len(records) == len(REQUIRED) and all(
            item["status"] == "matched" for item in records
        ) else "blocked",
        "checked": len(records),
        "files": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail closed on diverged Jeeves agent mirrors")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = check_parity()
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        for item in report["files"]:
            if item["status"] != "matched":
                print(f"{item['status']}: {item['name']}")
        print(f"jeeves agent mirror parity: {report['status']} ({report['checked']} files)")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
