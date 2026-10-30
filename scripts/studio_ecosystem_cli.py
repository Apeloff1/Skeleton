"""Read and compile original studio blueprints through canonical game_builder."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from skeleton.ai.game_builder.studio_ecosystem_catalog import (
    compile_preview, list_blueprints, read_blueprint,
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Browse original production briefs and build offline proof")
    ap.add_argument("--genre", help="Filter available production briefs")
    ap.add_argument("--biome", help="Filter original environments")
    ap.add_argument("--project", help="Inspect or compile one registered project")
    ap.add_argument("--compile-preview", action="store_true", help="Compile verified HTML5 maze preview")
    ap.add_argument("--materialize-batch", action="store_true",
                    help="Compile matching catalog projects into an existing output directory")
    ap.add_argument("--max-artifact-bytes", type=int, default=128 * 1024 * 1024,
                    help="Fail-closed maximum output bytes for batch exports")
    ap.add_argument("--output", type=Path, help="New directory for compiled HTML")
    args = ap.parse_args(argv)
    if args.materialize_batch:
        if args.compile_preview or not args.output:
            ap.error("--materialize-batch requires --output and excludes --compile-preview")
        from skeleton.ai.game_builder.studio_ecosystem_batch import materialize_previews
        result = materialize_previews(
            args.output, authorized=True, genre=args.genre, biome=args.biome,
            project_ids=(args.project,) if args.project else None,
            max_artifact_bytes=args.max_artifact_bytes,
        )
        print(json.dumps(result, sort_keys=True))
    elif args.compile_preview:
        if not args.project or not args.output:
            ap.error("--compile-preview requires --project and --output")
        if args.output.is_symlink() or args.output.exists():
            ap.error("--output must be a new, non-symlink location")
        project = compile_preview(args.project, authorized=True)
        from skeleton.ai.game_builder.playable_compiler import export_compiled_project
        args.output.mkdir(parents=True, exist_ok=False)
        export_compiled_project(project, args.output / "index.html", authorized=True)
        print(json.dumps({"project": args.project, "receipt": project.receipt()},
                         sort_keys=True))
    elif args.project:
        print(json.dumps(read_blueprint(args.project), sort_keys=True))
    else:
        print(json.dumps({"projects": list_blueprints(genre=args.genre, biome=args.biome)},
                         sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
