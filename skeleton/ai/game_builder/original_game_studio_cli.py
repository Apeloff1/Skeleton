"""Operator-only offline entry point for an original-to-consumer game studio run."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Sequence

from .authored_tiles import AUTHORED_SCHEMA, AuthoredGameError, read_authored_document
from .contracts import canonical_json
from .dual_runtime_export import DualRuntimeExportError
from .mirror_room_runtime import MirrorRoomError
from .original_game_studio import StudioError, export_studio_run, run_original_game_studio
from .playable_cli import MAX_INPUT_BYTES, _intent, _read_json
from .playable_compiler import PlayableCompilationError
from .playable_simulation import GameplayError
from .playable_world import PlayableWorldError
from .studio_tool_fabric import ToolFabricError


def parser() -> argparse.ArgumentParser:
    entry = argparse.ArgumentParser(
        prog="python -m skeleton.ai.game_builder.original_game_studio_cli",
        description="Build original playable game, run adversarial probes, practice and stage consumer handoff.",
    )
    entry.add_argument("--intent", required=True, help="Bounded original-game JSON intent")
    entry.add_argument("--output", required=True, help="New directory for browser+Godot project and evidence")
    entry.add_argument("--authored-world", help="Original editor-authored tile JSON")
    entry.add_argument("--human-reviewed", action="store_true",
                       help="Confirm original tile geometry human review")
    entry.add_argument("--mirror-attempts", type=int, default=128,
                       help="Real deterministic adversarial attempts, 64..512")
    entry.add_argument("--companion-practice", type=int, default=2,
                       help="Real original practice games, 0..8 (proof receipts only)")
    entry.add_argument("--trusted-local-operator", action="store_true",
                       help="Acknowledge separately established operator authorization")
    return entry


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if not args.trusted_local_operator:
        print("error: external operator authorization acknowledgement required", file=sys.stderr)
        return 2
    try:
        intent = _intent(_read_json(args.intent, MAX_INPUT_BYTES))
        authored = None
        if args.authored_world:
            payload = read_authored_document(args.authored_world, authorized=True)
            if (set(payload) != {"schema", "intent", "levels"}
                    or payload["schema"] != AUTHORED_SCHEMA
                    or payload["intent"] != intent.to_payload()):
                raise AuthoredGameError("authored tiles do not match original intent")
            authored = payload["levels"]
        elif args.human_reviewed:
            raise AuthoredGameError("--human-reviewed requires --authored-world")
        run = run_original_game_studio(
            intent, authorized=True,
            human_reviewed_tiles=authored,
            human_authored_approved=args.human_reviewed,
            mirror_attempts=args.mirror_attempts,
            companion_practice_games=args.companion_practice,
        )
        output = export_studio_run(run, str(Path(args.output)), authorized=True)
    except (StudioError, ToolFabricError, MirrorRoomError,
            AuthoredGameError, PlayableWorldError, PlayableCompilationError,
            GameplayError, DualRuntimeExportError, OSError) as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(canonical_json({
        "schema": "skeleton.game_builder.studio_cli_result.v1",
        "output": str(output),
        "studio_digest": run.digest,
        "world_digest": run.project.world.digest,
        "mirror_attempts": len(run.mirror.probes),
        "mirror_failures": len(run.mirror.failures),
        "verified_practice_games": len(run.practice),
        "consumer_status": run.consumer.to_payload()["status"],
        "consumer_blockers": list(run.consumer.blockers),
        "source_manifest_digest": run.package.manifest["manifest_digest"],
        "native_hardware_tested": False,
        "publication_authorized": False,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["parser", "main"]
