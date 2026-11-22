"""Read-only operator CLI for source-bound offline story checkpoint review.

The CLI reads only owner-private regular files in the current directory
through a pinned directory descriptor. No arbitrary paths, symlinks, FIFOs,
hardlinks, output writes, or network access are admitted.
"""
from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from typing import Sequence

from skeleton.ai.agents.jeeves.studio_story_checkpoint_tool import (
    REQUEST_SCHEMA, execute_story_checkpoint_tool,
)
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError

MAX_CHECKPOINT_BYTES = 65536


def _read_private_checkpoint(filename: str) -> str:
    """Pin the current directory and open one bounded nofollow regular file."""
    if (type(filename) is not str or not 1 <= len(filename) <= 255
            or filename in (".", "..") or "/" in filename or "\\" in filename
            or any(ord(char) < 32 or ord(char) == 127 for char in filename)):
        raise StudioQuestError("checkpoint must be a plain current-directory filename")
    if not all(hasattr(os, attr) for attr in ("O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK")):
        raise StudioQuestError("secure checkpoint input unavailable on this platform")
    directory = os.open(".", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fd = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                     dir_fd=directory)
        try:
            before = os.fstat(fd)
            if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                    or before.st_uid != os.geteuid()
                    or before.st_mode & 0o077
                    or not 1 <= before.st_size <= MAX_CHECKPOINT_BYTES):
                raise StudioQuestError("checkpoint must be a bounded owner-private regular file")
            with os.fdopen(os.dup(fd), "rb", closefd=True) as stream:
                raw = stream.read(MAX_CHECKPOINT_BYTES + 1)
            after = os.fstat(fd)
            identity = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
            if (len(raw) != before.st_size
                    or any(getattr(before, key) != getattr(after, key)
                           for key in identity)):
                raise StudioQuestError("checkpoint changed during bounded read")
        finally:
            os.close(fd)
    finally:
        os.close(directory)
    try:
        return raw.decode("utf-8", "strict")
    except UnicodeError as exc:
        raise StudioQuestError("invalid checkpoint UTF-8") from exc


def parser() -> argparse.ArgumentParser:
    entry = argparse.ArgumentParser(
        prog="python -m skeleton.ai.game_builder.studio_story_checkpoint_cli",
        description="Preview or compare source-bound original browser story checkpoints",
    )
    entry.add_argument("--project-id", required=True)
    entry.add_argument("--quest-source-digest", required=True)
    entry.add_argument("--checkpoint-file", required=True,
                       help="Owner-private regular JSON filename in current directory")
    mode = entry.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preview-stage")
    mode.add_argument("--compare-file",
                      help="Second owner-private JSON filename in current directory")
    entry.add_argument("--alternative",
                       help="Required for preview; forbidden for comparison")
    entry.add_argument("--trusted-local-operator", action="store_true",
                       help="Acknowledge separately established operator authorization")
    return entry


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if not args.trusted_local_operator:
        print("error: external operator authorization acknowledgement required",
              file=sys.stderr)
        return 2
    if (args.preview_stage is None) != (args.alternative is None):
        print("error: preview requires stage and alternative together", file=sys.stderr)
        return 2
    if args.compare_file is not None and args.alternative is not None:
        print("error: comparison forbids preview alternative", file=sys.stderr)
        return 2
    try:
        current = _read_private_checkpoint(args.checkpoint_file)
        candidate = (_read_private_checkpoint(args.compare_file)
                     if args.compare_file is not None else None)
        request = {
            "schema": REQUEST_SCHEMA,
            "project_id": args.project_id,
            "expected_quest_source_digest": args.quest_source_digest,
            "operation": "compare" if candidate is not None else "preview",
            "current_checkpoint": current,
            "candidate_checkpoint": candidate,
            "stage_id": args.preview_stage,
            "alternative": args.alternative,
        }
        result = execute_story_checkpoint_tool(request, authorized=True)
    except (StudioQuestError, OSError, UnicodeError, ValueError) as exc:
        print("error: " + str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, ensure_ascii=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
