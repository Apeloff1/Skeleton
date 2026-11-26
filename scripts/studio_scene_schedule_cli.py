"""Operator CLI: authored scene timing -> quest replay -> private bundle."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import (
    compile_scene_schedule, publish_scene_schedule, verify_scene_schedule,
)


def _strict(raw: str, *, max_bytes: int) -> object:
    if len(raw.encode("utf-8", "strict")) > max_bytes:
        raise StudioQuestError("scene schedule JSON exceeds byte budget")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise StudioQuestError("duplicate scene schedule JSON key")
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(
                              StudioQuestError("nonfinite scene schedule JSON")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("invalid scene schedule JSON") from exc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Original source-bound scene scheduler")
    ap.add_argument("--project", required=True)
    ap.add_argument("--expected-source", required=True)
    ap.add_argument("--expected-session")
    ap.add_argument("--actions", default="[]", help="Strict JSON authored quest history")
    ap.add_argument("--schedule", help="Strict JSON authored scene timing constraints")
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--publish-directory", type=Path,
                       help="Existing directory for exclusive private schedule publication")
    group.add_argument("--verify-directory", type=Path,
                       help="Existing directory containing a previously published schedule")
    args = ap.parse_args(argv)
    if args.verify_directory and args.schedule is not None:
        ap.error("--verify-directory uses persisted schedule; omit --schedule")
    if not args.verify_directory and args.schedule is None:
        ap.error("scene scheduling requires --schedule")
    try:
        actions = _strict(args.actions, max_bytes=16384)
        docs = read_blueprint(args.project)
        if args.verify_directory:
            result = verify_scene_schedule(
                docs, actions, args.verify_directory, authorized=True,
                expected_source_digest=args.expected_source)
            if args.expected_session is not None and result["session_digest"] != args.expected_session:
                raise StudioQuestError("stale restored schedule session lease")
        else:
            schedule = _strict(args.schedule, max_bytes=16384)
            result = compile_scene_schedule(
                docs, actions, schedule, authorized=True,
                expected_source_digest=args.expected_source,
                expected_session_digest=args.expected_session)
            if args.publish_directory:
                publication = publish_scene_schedule(
                    result, args.publish_directory, authorized=True,
                    documents=docs, actions=actions)
                result = {"schedule": result, "publication": publication}
    except (StudioQuestError, PermissionError, ValueError, TypeError, OSError,
            UnicodeError, RecursionError) as exc:
        ap.error(str(exc))
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
