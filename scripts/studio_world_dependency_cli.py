"""CLI for source-bound dependency-ordered original-world workflows."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

from scripts.studio_scene_schedule_cli import _strict
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_world_batch_editor import publish_world_batch_editor
from skeleton.ai.game_builder.studio_world_dependency import (
    compile_dependency_world_batch, execute_dependency_world_batch,
    publish_dependency_execution, restore_dependency_execution,
    render_dependency_world_html,
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Canonical original world dependency workflow")
    ap.add_argument("--expected-catalog", required=True)
    modes = ap.add_mutually_exclusive_group(required=True)
    modes.add_argument("--graph", help="Strict bounded typed dependency graph JSON")
    modes.add_argument("--restore", type=Path, help="Existing private execution directory")
    ap.add_argument("--publish", type=Path, help="Existing private output directory")
    ap.add_argument("--editor-directory", type=Path, help="Existing private editor directory")
    ap.add_argument("--html-sha256", action="store_true")
    args = ap.parse_args(argv)
    if args.restore and (args.publish or args.editor_directory):
        ap.error("restore is read-only; cannot combine with publication")
    try:
        if args.restore:
            execution = restore_dependency_execution(
                args.restore, authorized=True,
                expected_catalog_digest=args.expected_catalog,
            )
            proof = execution["dependency_proof"]
        else:
            graph = _strict(args.graph, max_bytes=48 * 1024)
            proof = compile_dependency_world_batch(
                graph, authorized=True,
                expected_catalog_digest=args.expected_catalog,
            )
            execution = execute_dependency_world_batch(proof, authorized=True)
        output: dict[str, object] = {
            "dependency_proof": proof, "execution": execution,
            "file_write_performed": False,
        }
        if args.html_sha256:
            output["html_sha256"] = sha256(render_dependency_world_html(
                proof, authorized=True)).hexdigest()
        if args.editor_directory:
            output["editor"] = publish_world_batch_editor(
                proof["plan"], args.editor_directory, authorized=True)
            output["file_write_performed"] = True
        if args.publish:
            output["publication"] = publish_dependency_execution(
                execution, args.publish, authorized=True)
            output["file_write_performed"] = True
    except (StudioQuestError, OSError, PermissionError, ValueError,
            TypeError, UnicodeError, RecursionError) as exc:
        ap.error(str(exc))
    print(json.dumps(output, sort_keys=True, separators=(",", ":"),
                     allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
