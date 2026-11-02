"""Operator-only three-way offline story checkpoint merge and private save.

All inputs are pinned, nofollow, owner-private files. Output is a new
owner-private file published without overwrite after verified canonical replay.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import stat
import sys
from typing import Sequence

from skeleton.ai.agents.jeeves.studio_story_merge_tool import (
    REQUEST_SCHEMA, execute_story_merge_tool,
)
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_story_checkpoint_cli import (
    _read_private_checkpoint,
)

_MAX_OUTPUT = 65536


def _basename(value: str) -> str:
    if (type(value) is not str or not 1 <= len(value) <= 255
            or value in (".", "..") or "/" in value or "\\" in value
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise StudioQuestError("output must be a plain current-directory filename")
    return value


def _publish_private(name: str, payload: str) -> None:
    name = _basename(name)
    data = payload.encode("utf-8", "strict")
    if not 1 <= len(data) <= _MAX_OUTPUT:
        raise StudioQuestError("merged output exceeds byte budget")
    if not all(hasattr(os, key) for key in (
            "O_DIRECTORY", "O_NOFOLLOW", "O_EXCL", "O_CLOEXEC")):
        raise StudioQuestError("secure output publication unavailable")
    directory = os.open(".", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    temporary = ".story-merge-" + secrets.token_hex(16)
    created = False
    try:
        metadata = os.fstat(directory)
        if (not stat.S_ISDIR(metadata.st_mode)
                or metadata.st_uid != os.geteuid()
                or metadata.st_mode & 0o077):
            raise StudioQuestError("output directory must be owner-private")
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                     | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=directory)
        created = True
        try:
            with os.fdopen(fd, "wb", closefd=True) as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        except BaseException:
            raise
        # link() is atomic and refuses an existing destination. Never use
        # replace()/rename() to overwrite a checkpoint from another fork.
        os.link(temporary, name, src_dir_fd=directory, dst_dir_fd=directory,
                follow_symlinks=False)
        try:
            os.fsync(directory)
        except OSError:
            # A failed directory durability barrier cannot leave an apparently
            # published but unacknowledged checkpoint behind.
            os.unlink(name, dir_fd=directory)
            raise
    finally:
        try:
            if created:
                os.unlink(temporary, dir_fd=directory)
                os.fsync(directory)
        finally:
            os.close(directory)


def parser() -> argparse.ArgumentParser:
    entry = argparse.ArgumentParser(
        prog="python -m skeleton.ai.game_builder.studio_story_checkpoint_merge_cli",
        description="Merge two original story forks without overwriting any checkpoint",
    )
    entry.add_argument("--project-id", required=True)
    entry.add_argument("--quest-source-digest", required=True)
    entry.add_argument("--ancestor-file", required=True)
    entry.add_argument("--current-file", required=True)
    entry.add_argument("--candidate-file", required=True)
    entry.add_argument("--output-file", required=True)
    entry.add_argument("--trusted-local-operator", action="store_true")
    return entry


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if not args.trusted_local_operator:
        print("error: external operator authorization required", file=sys.stderr)
        return 2
    try:
        names = [_basename(name) for name in (
            args.ancestor_file, args.current_file,
            args.candidate_file, args.output_file)]
        if len(set(names)) != 4:
            raise StudioQuestError("merge inputs and output must be distinct files")
        request = {
            "schema": REQUEST_SCHEMA,
            "project_id": args.project_id,
            "expected_quest_source_digest": args.quest_source_digest,
            "ancestor_checkpoint": _read_private_checkpoint(args.ancestor_file),
            "current_checkpoint": _read_private_checkpoint(args.current_file),
            "candidate_checkpoint": _read_private_checkpoint(args.candidate_file),
        }
        result = execute_story_merge_tool(request, authorized=True)
        proof = result["canonical_replay"]
        _publish_private(args.output_file, proof["merged_checkpoint"])
    except (StudioQuestError, OSError, UnicodeError, ValueError) as exc:
        print("error: " + str(exc), file=sys.stderr)
        return 2
    # Do not echo the private checkpoint contents or imply release approval.
    print(json.dumps({
        "schema": "skeleton.game_builder.story_merge_cli_receipt.v1",
        "project_id": args.project_id,
        "merged_session_digest": proof["merged_session_digest"],
        "merged_checkpoint_sha256": proof["merged_checkpoint_sha256"],
        "merged_action_count": proof["merged_action_count"],
        "saved_new_private_file": True,
        "release_certified": False,
    }, sort_keys=True, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
