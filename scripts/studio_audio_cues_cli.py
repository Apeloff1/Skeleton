"""Operator CLI for source-leased original scene audio and caption authoring."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_audio_cues import (
    compile_audio_cues, publish_audio_cues, verify_published_audio_cues,
)
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from scripts.studio_scene_schedule_cli import _strict


def _read_authoring(path: Path) -> object:
    if not hasattr(os, "O_NOFOLLOW"):
        raise StudioQuestError("secure authoring file reads unavailable")
    # The operator supplies a regular file, not a directory, FIFO or symlink.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        import stat
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise StudioQuestError("audio authoring input must be a regular file")
        data = os.read(fd, 65537)
        if len(data) > 65536:
            raise StudioQuestError("audio authoring input exceeds byte budget")
    finally:
        os.close(fd)
    return _strict(data.decode("utf-8", "strict"), max_bytes=65536)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Rehearse original scene audio captions with exact source leases")
    parser.add_argument("--project", required=True)
    parser.add_argument("--expected-source", required=True)
    parser.add_argument("--expected-session")
    parser.add_argument("--actions", default="[]")
    parser.add_argument("--schedule", required=True)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--authoring-json")
    inputs.add_argument("--authoring-file", type=Path)
    outputs = parser.add_mutually_exclusive_group()
    outputs.add_argument("--publish-directory", type=Path)
    outputs.add_argument("--verify-directory", type=Path)
    args = parser.parse_args(argv)
    try:
        documents = read_blueprint(args.project)
        actions = _strict(args.actions, max_bytes=16384)
        schedule = _strict(args.schedule, max_bytes=16384)
        authoring = (_read_authoring(args.authoring_file)
                     if args.authoring_file is not None
                     else _strict(args.authoring_json, max_bytes=65536))
        kwargs = {
            "authorized": True,
            "expected_source_digest": args.expected_source,
            "expected_session_digest": args.expected_session,
        }
        if args.verify_directory is not None:
            receipt = verify_published_audio_cues(
                args.verify_directory, documents=documents, actions=actions,
                schedule=schedule, request=authoring, **kwargs)
        else:
            receipt = compile_audio_cues(
                documents, actions, schedule, authoring, **kwargs)
            if args.publish_directory is not None:
                published = publish_audio_cues(
                    receipt, args.publish_directory, authorized=True,
                    documents=documents, actions=actions, schedule=schedule,
                    request=authoring)
                receipt = {"plan": receipt, "publication": published}
    except (StudioQuestError, ValueError, TypeError, OSError,
            UnicodeError, RecursionError, PermissionError) as exc:
        parser.error(str(exc))
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
