"""App-owned first playable source journey using the canonical game studio.

This deliberately has no model/provider SDK, native device execution, external
network access, store publication or rights certification. It builds a genuine
original game through the existing typed studio and replays its exported
browser/Godot source with the canonical verifier before reporting success.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Sequence

from skeleton.ai.game_builder.dual_runtime_export import DualRuntimeExportError
from skeleton.ai.game_builder.dual_runtime_verify import (
    DualRuntimeVerificationError, verify_exported_package,
)
from skeleton.ai.game_builder.offline_receipt_publication import (
    ReceiptPublicationError, preflight_receipt_destination, publish_verified_receipt,
)
from skeleton.ai.game_builder.original_game_studio import (
    StudioError, export_studio_run, run_original_game_studio,
)
from skeleton.ai.game_builder.playable_cli import MAX_INPUT_BYTES, _intent, _read_json
from skeleton.ai.game_builder.playable_compiler import PlayableCompilationError
from skeleton.ai.game_builder.playable_simulation import GameplayError
from skeleton.ai.game_builder.playable_world import PlayableWorldError
from skeleton.ai.game_builder.mirror_room_runtime import MirrorRoomError
from skeleton.ai.game_builder.studio_tool_fabric import ToolFabricError


SCHEMA = "skeleton.app.first_playable_journey.v1"
VERIFY_SCHEMA = "skeleton.app.first_playable_journey_verification.v1"


class FirstPlayableJourneyError(ValueError):
    """An original game could not be built and replay-verified for handoff."""


def build_first_playable_journey(
    intent_path: str | Path, destination: str | Path, *,
    authorized: bool, mirror_attempts: int = 64,
    practice_games: int = 0,
    receipt_destination: str | Path | None = None,
) -> dict[str, object]:
    """Build, export and independently reexecute one real original game.

    The expected release hash is captured from the trusted in-memory package
    before filesystem publication. It is independent of the later disk read,
    but is not an externally distributed signature or legal authorization.
    On a post-export failure the output is explicitly unqualified and left
    intact for operator inspection rather than deleting a possibly replaced
    directory or silently claiming a rollback.
    """
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    if type(mirror_attempts) is not int or not 64 <= mirror_attempts <= 512:
        raise FirstPlayableJourneyError("mirror attempt budget must be 64 to 512")
    if type(practice_games) is not int or not 0 <= practice_games <= 8:
        raise FirstPlayableJourneyError("practice game budget must be 0 to 8")
    if receipt_destination is not None:
        preflight_receipt_destination(
            receipt_destination, protected_roots=(destination,), authorized=True,
        )
    intent = _intent(_read_json(str(intent_path), MAX_INPUT_BYTES))
    run = run_original_game_studio(
        intent, authorized=True, mirror_attempts=mirror_attempts,
        companion_practice_games=practice_games,
    )
    if not run.mirror.passed or run.project.proof.final_state.status != "won":
        raise FirstPlayableJourneyError("canonical playable proof is incomplete")
    trusted_release = run.package.files.get("release.json")
    if type(trusted_release) is not bytes or not trusted_release:
        raise FirstPlayableJourneyError("canonical source release is missing")
    expected_pin = sha256(trusted_release).hexdigest()
    output = export_studio_run(run, str(destination), authorized=True)
    verified = verify_exported_package(
        output, expected_manifest_sha256=expected_pin, authorized=True,
    )
    if (
        verified.get("offline_gameplay_reexecuted") is not True
        or verified.get("manifest_sha256") != expected_pin
        or verified.get("project_id") != intent.project_id
        or verified.get("world_digest") != run.project.world.digest
        or verified.get("replay_digest") != run.project.proof.digest
        or verified.get("release_certified") is not False
        or verified.get("godot_executed") is not False
    ):
        raise FirstPlayableJourneyError(
            "exported source failed canonical identity and replay acceptance"
        )
    receipt_pin = None
    if receipt_destination is not None:
        receipt_pin = publish_verified_receipt(
            verified, receipt_destination, protected_roots=(output,),
            authorized=True,
        )
    return {
        "schema": SCHEMA,
        "status": "source_playable_verified_release_blocked",
        "project_id": intent.project_id,
        "output": str(output),
        "studio_digest": run.digest,
        "world_digest": run.project.world.digest,
        "trusted_in_process_manifest_sha256": expected_pin,
        "verified_source_files": verified["verified_files"],
        "replayed_actions": verified["replayed_actions"],
        "replay_digest": verified["replay_digest"],
        "offline_gameplay_reexecuted": True,
        "model_inference_observed": False,
        "native_godot_executed": False,
        "native_device_qualified": False,
        "rights_certified": False,
        "release_certified": False,
        "consumer_blockers": list(run.consumer.blockers),
        "pin_distribution_required": True,
        "verification_receipt": verified,
        "receipt_file": str(receipt_destination) if receipt_pin is not None else None,
        "independent_receipt_sha256": receipt_pin,
    }



def verify_existing_playable_journey(
    source_directory: str | Path, *, expected_manifest_sha256: str,
    authorized: bool, receipt_destination: str | Path | None = None,
) -> dict[str, object]:
    """Reopen and reexecute an existing game using an independently held pin.

    Unlike a build, this path never creates or modifies the source package.
    Verification is bounded by the canonical game-builder source verifier and
    cannot turn a source-level proof into device, rights or release approval.
    """
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    if receipt_destination is not None:
        preflight_receipt_destination(
            receipt_destination, protected_roots=(source_directory,),
            authorized=True,
        )
    verified = verify_exported_package(
        source_directory, expected_manifest_sha256=expected_manifest_sha256,
        authorized=True,
    )
    if (verified.get("offline_gameplay_reexecuted") is not True
            or verified.get("manifest_sha256") != expected_manifest_sha256
            or verified.get("release_certified") is not False
            or verified.get("godot_executed") is not False):
        raise FirstPlayableJourneyError("existing game source replay did not qualify")
    receipt_pin = None
    if receipt_destination is not None:
        receipt_pin = publish_verified_receipt(
            verified, receipt_destination, protected_roots=(source_directory,),
            authorized=True,
        )
    return {
        "schema": VERIFY_SCHEMA,
        "status": "existing_source_playable_verified_release_blocked",
        "project_id": verified["project_id"],
        "source_directory": str(source_directory),
        "independent_manifest_sha256": expected_manifest_sha256,
        "verified_source_files": verified["verified_files"],
        "replayed_actions": verified["replayed_actions"],
        "world_digest": verified["world_digest"],
        "replay_digest": verified["replay_digest"],
        "offline_gameplay_reexecuted": True,
        "model_inference_observed": False,
        "native_godot_executed": False,
        "native_device_qualified": False,
        "rights_certified": False,
        "release_certified": False,
        "verification_receipt": verified,
        "receipt_file": str(receipt_destination) if receipt_pin is not None else None,
        "independent_receipt_sha256": receipt_pin,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton app studio-journey",
        description="Build an original game, export browser/Godot source and replay-verify it offline.",
    )
    parser.add_argument("--intent", help="bounded original game intent JSON for new builds")
    parser.add_argument("--verify-existing", action="store_true",
                        help="read-only re-verification of an existing exported game")
    parser.add_argument("--expected-manifest-sha256",
                        help="independent SHA-256 pin required for --verify-existing")
    parser.add_argument("--output", required=True, help="new destination directory")
    parser.add_argument("--mirror-attempts", type=int, default=64)
    parser.add_argument("--practice-games", type=int, default=0)
    parser.add_argument("--receipt", help="new owner-private .json receipt outside game package")
    parser.add_argument(
        "--trusted-local-operator", action="store_true",
        help="acknowledge separately established local operator authority",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.verify_existing:
            if args.intent is not None or args.mirror_attempts != 64 or args.practice_games != 0:
                raise FirstPlayableJourneyError(
                    "existing verification cannot build or tune a new game"
                )
            receipt = verify_existing_playable_journey(
                args.output, expected_manifest_sha256=args.expected_manifest_sha256,
                authorized=args.trusted_local_operator,
                receipt_destination=args.receipt,
            )
        else:
            if args.intent is None or args.expected_manifest_sha256 is not None:
                raise FirstPlayableJourneyError(
                    "new game builds require --intent and reject external verification pins"
                )
            receipt = build_first_playable_journey(
                args.intent, args.output,
                authorized=args.trusted_local_operator,
                mirror_attempts=args.mirror_attempts,
                practice_games=args.practice_games,
                receipt_destination=args.receipt,
            )
    except (
        FirstPlayableJourneyError, StudioError, PlayableWorldError,
        PlayableCompilationError, GameplayError, MirrorRoomError,
        ToolFabricError, DualRuntimeExportError, DualRuntimeVerificationError,
        ReceiptPublicationError,
        PermissionError, OSError, TypeError, ValueError,
    ) as exc:
        # Do not print supplied input, credentials, arbitrary filesystem
        # contents or an unqualified output path as a successful handoff.
        print(json.dumps({
            "schema": SCHEMA, "status": "blocked",
            "error": type(exc).__name__, "source_playable_verified": False,
            "release_certified": False,
        }, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["SCHEMA", "VERIFY_SCHEMA", "FirstPlayableJourneyError", "build_first_playable_journey", "verify_existing_playable_journey", "main"]
