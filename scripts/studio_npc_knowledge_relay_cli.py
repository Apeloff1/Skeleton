"""Strict offline CLI for source-bound NPC knowledge relay and private editing."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import _open_directory
from skeleton.ai.game_builder.studio_ecosystem_npc_knowledge_relay import (
    PROMPT, MAX_BYTES, compile_npc_knowledge_relay, propose_npc_knowledge_relay,
    replay_npc_knowledge_relay, compile_npc_relay_playable,
    publish_npc_knowledge_relay, restore_npc_knowledge_relay,
)
from skeleton.ai.game_builder.studio_ecosystem_npc_knowledge_relay_editor import (
    publish_npc_relay_editor, load_npc_relay_editor_export,
)


def _private_json(path: Path, limit: int) -> dict[str, object]:
    if not isinstance(path, Path):
        raise StudioQuestError("NPC relay JSON path must be typed")
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    parent_fd = _open_directory(path.parent)
    try:
        fd = os.open(path.name, flags, dir_fd=parent_fd)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= limit
                    or (os.name == "posix" and
                        (info.st_uid != os.getuid() or info.st_mode & 0o077
                         or info.st_nlink != 1))):
                raise StudioQuestError("NPC relay JSON must be a private regular file")
            raw = os.read(fd, limit + 1)
        finally:
            os.close(fd)
    finally:
        os.close(parent_fd)
    if not raw or len(raw) > limit:
        raise StudioQuestError("invalid bounded NPC relay JSON file")
    def unique(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise StudioQuestError("duplicate NPC relay JSON key")
            out[key] = value
        return out
    try:
        result = json.loads(
            raw.decode("utf-8", "strict"), object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(
                StudioQuestError("nonfinite NPC relay JSON")))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise StudioQuestError("invalid NPC relay JSON") from exc
    if type(result) is not dict:
        raise StudioQuestError("NPC relay JSON root must be an object")
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Source-replayed NPC knowledge relay")
    ap.add_argument("--project", required=True)
    ap.add_argument("--expected-source", required=True)
    ap.add_argument("--exchange-file", type=Path,
                    help="Private canonical knowledge exchange receipt")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prompt", action="store_true",
                      help="Deterministically propose source-supported relay routes")
    mode.add_argument("--authoring-file", type=Path,
                      help="Private edited typed JSON authoring file")
    mode.add_argument("--editor-export-file", type=Path,
                      help="Source-bound JSON exported from offline HTML editor")
    mode.add_argument("--restore", type=Path,
                      help="Restore private canonical relay receipt from directory")
    ap.add_argument("--publish", type=Path, help="Publish immutable private relay receipt")
    ap.add_argument("--baseline-relay-file", type=Path,
                    help="Private canonical baseline receipt for editor import")
    ap.add_argument("--render-editor", type=Path,
                    help="Write immutable CSP-protected offline editor to directory")
    ap.add_argument("--playable", action="store_true",
                    help="Require a verified playable handoff manifest")
    args = ap.parse_args(argv)
    if args.restore is not None and (args.publish is not None or
                                     args.exchange_file is not None or
                                     args.baseline_relay_file is not None):
        ap.error("restore cannot accept a new exchange or publication")
    if args.restore is None and args.exchange_file is None:
        ap.error("new relay requires --exchange-file")
    if (args.editor_export_file is not None) != (args.baseline_relay_file is not None):
        ap.error("editor import requires matching --baseline-relay-file")
    try:
        docs = read_blueprint(args.project)
        if args.restore is not None:
            relay = restore_npc_knowledge_relay(
                docs, args.restore, authorized=True,
                expected_source_digest=args.expected_source)
        else:
            exchange = _private_json(args.exchange_file, MAX_BYTES)
            if args.prompt:
                relay = propose_npc_knowledge_relay(
                    docs, exchange, PROMPT, authorized=True,
                    expected_source_digest=args.expected_source)
            else:
                if args.editor_export_file is not None:
                    baseline = _private_json(args.baseline_relay_file, MAX_BYTES)
                    replay_npc_knowledge_relay(docs, baseline, authorized=True)
                    if (baseline["exchange_digest"] != exchange["exchange_digest"]
                            or baseline["source_digest"] != args.expected_source):
                        raise StudioQuestError("editor baseline differs from exchange source")
                    authoring = load_npc_relay_editor_export(
                        args.editor_export_file, authorized=True,
                        expected_project_id=args.project,
                        expected_source_digest=args.expected_source,
                        expected_session_digest=baseline["session_digest"],
                        expected_exchange_digest=baseline["exchange_digest"],
                        expected_baseline_digest=baseline["relay_digest"])
                else:
                    authoring = _private_json(args.authoring_file, 32768)
                relay = compile_npc_knowledge_relay(
                    docs, exchange, authoring, authorized=True,
                    expected_source_digest=args.expected_source)
            replay_npc_knowledge_relay(docs, relay, authorized=True)
        result: dict[str, object] = {
            "schema": "skeleton.cli.studio_npc_knowledge_relay.v1",
            "relay": relay, "file_write_performed": False,
            "release_certified": False,
        }
        if args.playable:
            result["playable_handoff"] = compile_npc_relay_playable(
                docs, relay, authorized=True)
        if args.render_editor is not None:
            result["editor"] = publish_npc_relay_editor(
                docs, relay, args.render_editor, authorized=True)
            result["file_write_performed"] = True
        if args.publish is not None:
            result["publication"] = publish_npc_knowledge_relay(
                docs, relay, args.publish, authorized=True)
            result["file_write_performed"] = True
        print(json.dumps(result, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False))
    except (StudioQuestError, PermissionError, OSError, ValueError,
            UnicodeError, RecursionError) as exc:
        ap.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
