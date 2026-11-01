"""Operator CLI for replay-verified NPC dialogue choice and private save."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat

from scripts.studio_scene_schedule_cli import _strict
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import _open_directory
from skeleton.ai.game_builder.studio_npc_dialogue_choice_commit import (
    MAX_BYTES, compile_npc_dialogue_choice_commit,
    publish_npc_dialogue_choice_commit, restore_npc_dialogue_choice_commit,
    render_npc_dialogue_choice_commit_html,
)


def _read_private_contact(path: Path) -> object:
    """Read a private receipt without following a caller-controlled symlink."""
    directory = _open_directory(path.parent)
    try:
        handle = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW |
                         os.O_NONBLOCK, dir_fd=directory)
        try:
            info = os.fstat(handle)
            if (not stat.S_ISREG(info.st_mode)
                    or not 0 < info.st_size <= MAX_BYTES
                    or (os.name == "posix" and
                        (info.st_uid != os.getuid() or info.st_mode & 0o077
                         or info.st_nlink != 1))):
                raise StudioQuestError("NPC dialogue contact input must be private")
            raw = os.read(handle, MAX_BYTES + 1)
            after = os.fstat(handle)
            if (len(raw) != info.st_size or after.st_size != info.st_size
                    or after.st_mtime_ns != info.st_mtime_ns
                    or after.st_ctime_ns != info.st_ctime_ns
                    or after.st_ino != info.st_ino):
                raise StudioQuestError("NPC dialogue contact input changed during read")
        finally:
            os.close(handle)
    finally:
        os.close(directory)
    return _strict(raw.decode("utf-8", "strict"), max_bytes=MAX_BYTES)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Commit one replay-verified original NPC dialogue choice")
    parser.add_argument("--project", required=True)
    parser.add_argument("--expected-contact", required=True)
    parser.add_argument("--expected-source", required=True)
    parser.add_argument("--expected-walk", required=True)
    parser.add_argument("--expected-quest", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--contact-json")
    mode.add_argument("--contact-file", type=Path)
    mode.add_argument("--restore", type=Path)
    parser.add_argument("--alternative")
    parser.add_argument("--publish", type=Path)
    parser.add_argument("--html-preview", action="store_true")
    args = parser.parse_args(argv)
    if args.html_preview and args.publish:
        parser.error("read-only HTML preview cannot publish")
    if args.restore and (args.publish or args.alternative):
        parser.error("restore cannot also compile or publish")
    if (args.contact_json is not None or args.contact_file is not None) and not args.alternative:
        parser.error("commit requires an authored alternative")
    params = {
        "authorized": True,
        "expected_contact_digest": args.expected_contact,
        "expected_source_digest": args.expected_source,
        "expected_walk_digest": args.expected_walk,
        "expected_quest_digest": args.expected_quest,
    }
    try:
        documents = read_blueprint(args.project)
        if args.restore:
            result = restore_npc_dialogue_choice_commit(
                documents, args.restore, **params)
        else:
            contact = (_read_private_contact(args.contact_file)
                       if args.contact_file is not None else
                       _strict(args.contact_json, max_bytes=MAX_BYTES))
            result = compile_npc_dialogue_choice_commit(
                documents, contact, alternative=args.alternative, **params)
        output: dict[str, object] = {
            "choice_commit": result, "file_write_performed": False,
        }
        if args.publish:
            output["publication"] = publish_npc_dialogue_choice_commit(
                documents, result, args.publish, **params)
            output["file_write_performed"] = True
    except (StudioQuestError, PermissionError, OSError, ValueError,
            TypeError, KeyError, UnicodeError, RecursionError) as exc:
        parser.error(str(exc))
    if args.html_preview:
        print(render_npc_dialogue_choice_commit_html(
            documents, result, **params).decode("utf-8"))
    else:
        print(json.dumps(output, sort_keys=True, separators=(",", ":"),
                         allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
