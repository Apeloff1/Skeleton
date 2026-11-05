"""App-owned first playable source journey using the canonical game studio.

This deliberately has no model/provider SDK, native device execution, external
network access, store publication or rights certification. It builds a genuine
original game through the existing typed studio and replays its exported
browser/Godot source with the canonical verifier before reporting success.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import hmac
import json
import os
import re
from pathlib import Path
import sys
from typing import Sequence

from skeleton.ai.game_builder.dual_runtime_export import DualRuntimeExportError
from skeleton.ai.game_builder.dual_runtime_verify import (
    DualRuntimeVerificationError, _assert_original_root, _read, _root_fd, verify_exported_package,
    load_verified_playable_world,
)
from skeleton.ai.game_builder.offline_receipt_inspection import (
    ReceiptInspectionError, inspect_verified_receipt,
)
from skeleton.ai.game_builder.offline_receipt_publication import (
    ReceiptPublicationError, preflight_receipt_destination, publish_verified_receipt,
)
from skeleton.ai.game_builder.original_game_studio import (
    StudioError, export_studio_run, run_original_game_studio,
)
from skeleton.ai.game_builder.playable_cli import (
    MAX_INPUT_BYTES, _intent, _object_pairs,
)
from skeleton.ai.game_builder.secure_export_publication import (
    AtomicDirectoryPublicationError, preflight_generated_tree_destination,
)
from skeleton.ai.game_builder.playable_compiler import PlayableCompilationError
from skeleton.ai.game_builder.playable_simulation import (
    GameplayError, deserialize_replay, play_actions, replay_prefix, resume_replay,
    serialize_replay,
)
from skeleton.app.private_game_save import (
    PrivateGameSaveError, publish_private_game_save, read_private_game_save,
)
from skeleton.app.offline_save_comparison import (
    OfflineSaveComparisonError, compare_verified_offline_saves,
)
from skeleton.app.offline_delivery_archive import (
    OfflineGameArchiveError, publish_offline_game_archive,
    inspect_offline_game_archive,
)
from skeleton.app.offline_archive_install import (
    OfflineSourceInstallError, install_offline_game_source,
    preflight_offline_game_install,
)
from skeleton.app.offline_install_reconciliation import (
    OfflineInstallReconciliationError, reconcile_installed_game_archive,
)
from skeleton.app.offline_install_quarantine import (
    OfflineInstallQuarantineError, inspect_offline_install_quarantine,
)
from skeleton.app.offline_progress_compatibility import (
    verify_archived_progress_binding,
)
from skeleton.app.offline_progress_migration import (
    OfflineProgressMigrationError, migrate_offline_game_progress,
    preflight_offline_game_migration,
)
from skeleton.app.offline_progress_recovery import (
    OfflineProgressReconciliationError, reconcile_migrated_offline_progress,
)
from skeleton.ai.game_builder.playable_world import GameBuildIntent, PlayableWorldError
from skeleton.ai.game_builder.mirror_room_runtime import MirrorRoomError
from skeleton.ai.game_builder.studio_tool_fabric import ToolFabricError


SCHEMA = "skeleton.app.first_playable_journey.v1"
VERIFY_SCHEMA = "skeleton.app.first_playable_journey_verification.v1"
INSPECT_SCHEMA = "skeleton.app.first_playable_receipt_inspection.v1"
RECONCILE_SCHEMA = "skeleton.app.first_playable_receipt_reconciliation.v1"
PLAY_SCHEMA = "skeleton.app.offline_source_gameplay.v1"


class FirstPlayableJourneyError(ValueError):
    """An original game could not be built and replay-verified for handoff."""



def _load_operator_intent(
    path: str | Path, *, expected_sha256: str | None = None,
) -> GameBuildIntent:
    """Read a bounded original intent from stable nofollow file descriptors.

    The shared game CLI's path-based JSON helper is not used here: a normal
    stat/read path can race a symlink replacement during first-run import.
    """
    if expected_sha256 is not None and (
        type(expected_sha256) is not str
        or re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None
    ):
        raise FirstPlayableJourneyError("independent lowercase intent SHA-256 required")
    source = Path(path).expanduser().absolute()
    if source.name in ("", ".", ".."):
        raise FirstPlayableJourneyError("invalid intent filename")
    try:
        parent_fd = _root_fd(source.parent)
    except (OSError, TypeError, ValueError) as exc:
        raise FirstPlayableJourneyError("unsafe intent parent") from exc
    try:
        # Two equal byte reads are insufficient: the input can be replaced by
        # a different inode containing identical JSON between opens. Capture
        # identity through the already pinned nofollow parent descriptor.
        before = os.stat(source.name, dir_fd=parent_fd, follow_symlinks=False)
        raw = _read(
            parent_fd, source.name, MAX_INPUT_BYTES, owner_controlled=True,
        )
        if _read(
            parent_fd, source.name, MAX_INPUT_BYTES, owner_controlled=True,
        ) != raw:
            raise FirstPlayableJourneyError("original game intent changed during import")
        after = os.stat(source.name, dir_fd=parent_fd, follow_symlinks=False)
        def identity(info):
            return (info.st_dev, info.st_ino, info.st_size, info.st_nlink,
                    info.st_uid, info.st_mode, info.st_mtime_ns, info.st_ctime_ns)
        if identity(before) != identity(after):
            raise FirstPlayableJourneyError("original game intent inode changed during import")
        if (expected_sha256 is not None and not hmac.compare_digest(
            sha256(raw).hexdigest(), expected_sha256,
        )):
            raise FirstPlayableJourneyError("original intent differs from independent pin")
        _assert_original_root(source.parent, parent_fd)
    finally:
        os.close(parent_fd)
    try:
        payload = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_object_pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(
                FirstPlayableJourneyError("nonfinite intent value")
            ),
        )
    except (UnicodeError, ValueError, TypeError, RecursionError) as exc:
        raise FirstPlayableJourneyError("invalid bounded intent JSON") from exc
    if type(payload) is not dict:
        raise FirstPlayableJourneyError("original intent must be a JSON object")
    return _intent(payload)


def build_first_playable_journey(
    intent_path: str | Path | GameBuildIntent, destination: str | Path, *,
    authorized: bool, mirror_attempts: int = 64,
    practice_games: int = 0,
    receipt_destination: str | Path | None = None,
    expected_intent_sha256: str | None = None,
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
    preflight_generated_tree_destination(destination)
    if receipt_destination is not None:
        preflight_receipt_destination(
            receipt_destination, protected_roots=(destination,), authorized=True,
        )
    if isinstance(intent_path, GameBuildIntent):
        if expected_intent_sha256 is not None:
            raise FirstPlayableJourneyError("in-memory onboarding has no pinned input file")
        intent = intent_path
    else:
        intent = _load_operator_intent(
            intent_path, expected_sha256=expected_intent_sha256,
        )
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
        "original_intent_independently_pinned": expected_intent_sha256 is not None,
        "independent_intent_sha256": expected_intent_sha256,
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



def inspect_first_playable_receipt(
    receipt_path: str | Path, *, expected_sha256: str, authorized: bool,
) -> dict[str, object]:
    """Inspect an archived replay receipt without replaying source or trusting it."""
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    verified = inspect_verified_receipt(
        receipt_path, expected_sha256=expected_sha256, authorized=True,
    )
    if (verified.get("receipt_integrity_verified") is not True
            or verified.get("gameplay_reexecuted_now") is not False
            or verified.get("release_certified") is not False):
        raise FirstPlayableJourneyError("archived receipt integrity is unqualified")
    return {
        "schema": INSPECT_SCHEMA,
        "status": "archived_receipt_integrity_verified_not_replayed",
        "receipt_sha256": expected_sha256,
        "receipt_schema": verified["receipt_schema"],
        "receipt_integrity_verified": True,
        "gameplay_reexecuted_now": False,
        "native_device_qualified": False,
        "rights_certified": False,
        "release_certified": False,
        "canonical_inspection": verified,
    }


def reconcile_first_playable_receipt(
    source_directory: str | Path, receipt_path: str | Path, *,
    expected_manifest_sha256: str, expected_receipt_sha256: str,
    authorized: bool,
) -> dict[str, object]:
    """Bind an independently pinned historical receipt to fresh source replay.

    The second full canonical verification detects source mutation between
    reading the historical receipt and completing reconciliation. Both reads
    are read-only, bounded and descriptor-safe on supported POSIX hosts.
    This is point-in-time evidence, not a persistent lock or release grant.
    """
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    before = verify_exported_package(
        source_directory, expected_manifest_sha256=expected_manifest_sha256,
        authorized=True,
    )
    inspected = inspect_verified_receipt(
        receipt_path, expected_sha256=expected_receipt_sha256,
        expected_source=before, authorized=True,
    )
    if inspected.get("source_binding_verified") is not True:
        raise FirstPlayableJourneyError("archived receipt is not bound to live source")
    after = verify_exported_package(
        source_directory, expected_manifest_sha256=expected_manifest_sha256,
        authorized=True,
    )
    if before != after:
        raise FirstPlayableJourneyError("game source changed during reconciliation")
    return {
        "schema": RECONCILE_SCHEMA,
        "status": "historical_receipt_bound_to_fresh_replay_release_blocked",
        "project_id": after["project_id"],
        "manifest_sha256": expected_manifest_sha256,
        "receipt_sha256": expected_receipt_sha256,
        "world_digest": after["world_digest"],
        "replay_digest": after["replay_digest"],
        "verified_source_files": after["verified_files"],
        "replayed_actions": after["replayed_actions"],
        "receipt_integrity_verified": True,
        "receipt_source_binding_verified": True,
        "offline_gameplay_reexecuted": True,
        "model_inference_observed": False,
        "native_godot_executed": False,
        "native_device_qualified": False,
        "rights_certified": False,
        "release_certified": False,
    }


def play_existing_source_game(
    source_directory: str | Path, *, expected_manifest_sha256: str,
    authorized: bool, moves: Sequence[str] = (),
    load_save: str | Path | None = None,
    expected_save_sha256: str | None = None,
    save_destination: str | Path | None = None,
    fork_at_step: int | None = None,
) -> dict[str, object]:
    """Execute actual offline player moves on a verified source-bound world.

    A save is a canonical hash-chained replay, not a trusted state snapshot.
    Restores reexecute every recorded move; fresh actions are appended only
    after canonical verification. New saves are private and no-clobber.
    """
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    if (type(moves) not in (tuple, list) or len(moves) > 512
            or any(type(move) is not str or move not in (
                "up", "down", "left", "right",
            ) for move in moves)):
        raise FirstPlayableJourneyError("invalid bounded offline player moves")
    if fork_at_step is not None and (
        type(fork_at_step) is not int or fork_at_step < 0 or load_save is None
    ):
        raise FirstPlayableJourneyError("fork requires a saved verified replay and nonnegative step")
    if (load_save is None) != (expected_save_sha256 is None):
        raise FirstPlayableJourneyError("restoring a save requires independent pin")
    if save_destination is not None:
        preflight_receipt_destination(
            save_destination, protected_roots=(source_directory,), authorized=True,
        )
    world = load_verified_playable_world(
        source_directory, expected_manifest_sha256=expected_manifest_sha256,
        authorized=True,
    )
    if load_save is None:
        replay = play_actions(world, (), authorized=True)
    else:
        data = read_private_game_save(
            load_save, expected_sha256=expected_save_sha256, authorized=True,
        )
        replay = deserialize_replay(world, data, authorized=True)
        if fork_at_step is not None:
            replay = replay_prefix(world, replay, fork_at_step, authorized=True)
    replay = resume_replay(world, replay, moves, authorized=True)
    save_pin = None
    if save_destination is not None:
        data = serialize_replay(world, replay, authorized=True)
        # Fail before publishing a save if the source changed while the
        # player was replaying. The post-publication verification below
        # remains mandatory; neither check is a native device claim.
        before_save = verify_exported_package(
            source_directory, expected_manifest_sha256=expected_manifest_sha256,
            authorized=True,
        )
        if before_save.get("world_digest") != world.digest:
            raise FirstPlayableJourneyError("source changed before save publication")
        save_pin = publish_private_game_save(
            data, save_destination, protected_roots=(source_directory,),
            authorized=True,
        )
    # Source must still be the pinned game after gameplay/save publication.
    final = verify_exported_package(
        source_directory, expected_manifest_sha256=expected_manifest_sha256,
        authorized=True,
    )
    if final.get("world_digest") != world.digest:
        raise FirstPlayableJourneyError("source changed during offline play")
    return {
        "schema": PLAY_SCHEMA,
        "status": "offline_gameplay_replayed_release_blocked",
        "project_id": world.intent.project_id,
        "manifest_sha256": expected_manifest_sha256,
        "world_digest": world.digest,
        "replay_digest": replay.digest,
        "action_count": len(replay.action_receipts),
        "final_state": replay.final_state.to_payload(),
        "save_file": str(save_destination) if save_pin is not None else None,
        "independent_save_sha256": save_pin,
        "offline_gameplay_reexecuted": True,
        "model_inference_observed": False,
        "native_godot_executed": False,
        "native_device_qualified": False,
        "rights_certified": False,
        "release_certified": False,
    }


def _parse_moves(value: str | None) -> tuple[str, ...]:
    if value is None or value == "":
        return ()
    if type(value) is not str or len(value) > 4096:
        raise FirstPlayableJourneyError("offline move list exceeds byte budget")
    moves = tuple(value.split(","))
    if len(moves) > 512 or any(
        move not in ("up", "down", "left", "right") for move in moves
    ):
        raise FirstPlayableJourneyError("invalid offline player action list")
    return moves


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton app studio-journey",
        description="Build an original game, export browser/Godot source and replay-verify it offline.",
    )
    parser.add_argument("--intent", help="bounded original game intent JSON for new builds")
    parser.add_argument("--expected-intent-sha256",
                        help="independently held SHA-256 for a new JSON intent build only")
    parser.add_argument("--onboard", action="store_true",
                        help="build an original offline game from typed first-run CLI inputs")
    parser.add_argument("--project-id", help="stable original game project ID for --onboard")
    parser.add_argument("--title", help="original game title for --onboard")
    parser.add_argument("--subtitle", help="original game subtitle for --onboard")
    parser.add_argument("--seed", type=int, help="deterministic world seed for --onboard")
    parser.add_argument("--theme", help="canonical original-game theme for --onboard")
    parser.add_argument("--width", type=int, help="odd game width for --onboard")
    parser.add_argument("--height", type=int, help="odd game height for --onboard")
    parser.add_argument("--levels", type=int, help="level count for --onboard")
    parser.add_argument("--verify-existing", action="store_true",
                        help="read-only re-verification of an existing exported game")
    parser.add_argument("--play-existing", action="store_true",
                        help="run bounded player moves on independently verified offline game source")
    parser.add_argument("--compare-saves", action="store_true",
                        help="read-only compare two independently pinned private replay histories")
    parser.add_argument("--package-existing", action="store_true",
                        help="publish a deterministic verified browser/Godot source ZIP")
    parser.add_argument("--install-archive", action="store_true",
                        help="install an independently pinned source ZIP into a new private game directory")
    parser.add_argument("--reconcile-install", action="store_true",
                        help="read-only verify installed game bytes against pinned delivery ZIP")
    parser.add_argument("--preflight-install", action="store_true",
                        help="read-only check pinned archive and unused install destination")
    parser.add_argument("--inspect-install-quarantine", action="store_true",
                        help="read-only inspect missing, extra or corrupt partial install files")
    parser.add_argument("--migrate-progress", action="store_true",
                        help="install pinned source ZIP and reexecute a separately pinned private replay")
    parser.add_argument("--check-archive-save", action="store_true",
                        help="read-only replay of a pinned private save against a pinned original source ZIP")
    parser.add_argument("--preflight-migration", action="store_true",
                        help="read-only pinned archive/save and destination admission")
    parser.add_argument("--reconcile-migration", action="store_true",
                        help="read-only reconciliation of independently pinned installed source and replay")
    parser.add_argument("--inspect-archive", action="store_true",
                        help="read-only integrity inspection of a separately pinned source ZIP")
    parser.add_argument("--archive", help="new or existing owner-private ZIP destination")
    parser.add_argument("--expected-archive-sha256",
                        help="independent archive digest required for inspection")
    parser.add_argument("--left-save", help="first owner-private offline replay save")
    parser.add_argument("--left-sha256", help="independent SHA-256 of first save")
    parser.add_argument("--right-save", help="second owner-private offline replay save")
    parser.add_argument("--right-sha256", help="independent SHA-256 of second save")
    parser.add_argument("--moves",
                        help="comma-separated up/down/left/right controls for --play-existing")
    parser.add_argument("--load-save",
                        help="previous private canonical replay save for --play-existing")
    parser.add_argument("--expected-save-sha256",
                        help="independently held save digest required by --load-save")
    parser.add_argument("--fork-at", type=int,
                        help="fork a verified loaded save at an earlier action boundary")
    parser.add_argument("--save",
                        help="new owner-private no-clobber replay save .json destination")
    parser.add_argument("--reconcile-receipt", action="store_true",
                        help="bind an archived receipt to freshly replayed source using two independent pins")
    parser.add_argument("--inspect-receipt", action="store_true",
                        help="read-only inspection of an independently pinned archived receipt")
    parser.add_argument("--expected-manifest-sha256",
                        help="independent SHA-256 pin required for --verify-existing")
    parser.add_argument("--expected-receipt-sha256",
                        help="independent SHA-256 pin required for --inspect-receipt")
    parser.add_argument("--output",
                        help="new export destination or existing game package")
    parser.add_argument("--mirror-attempts", type=int, default=64)
    parser.add_argument("--practice-games", type=int, default=0)
    parser.add_argument("--receipt",
                        help="new owner-private receipt or existing receipt to inspect")
    parser.add_argument(
        "--trusted-local-operator", action="store_true",
        help="acknowledge separately established local operator authority",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.expected_intent_sha256 is not None and (
            args.intent is None or args.onboard or any((
                args.verify_existing, args.play_existing, args.compare_saves,
                args.package_existing, args.install_archive, args.reconcile_install,
                args.preflight_install, args.inspect_install_quarantine,
                args.migrate_progress, args.check_archive_save,
                args.preflight_migration, args.reconcile_migration,
                args.inspect_archive, args.inspect_receipt, args.reconcile_receipt,
            ))
        ):
            raise FirstPlayableJourneyError(
                "independent intent pin is only valid for new JSON game builds"
            )
        onboarding_values = (
            args.project_id, args.title, args.subtitle, args.seed,
            args.theme, args.width, args.height, args.levels,
        )
        comparison_values = (
            args.left_save, args.left_sha256, args.right_save, args.right_sha256,
        )
        if args.inspect_install_quarantine:
            if (args.preflight_install or args.reconcile_install
                    or args.check_archive_save or args.install_archive
                    or args.package_existing or args.inspect_archive
                    or args.play_existing or args.compare_saves
                    or args.verify_existing or args.reconcile_receipt
                    or args.inspect_receipt or args.onboard or args.migrate_progress
                    or args.preflight_migration or args.reconcile_migration
                    or args.output is None or args.archive is None
                    or args.expected_archive_sha256 is None
                    or args.expected_manifest_sha256 is None
                    or args.intent is not None or args.receipt is not None
                    or args.expected_receipt_sha256 is not None
                    or args.moves is not None or args.load_save is not None
                    or args.expected_save_sha256 is not None
                    or args.save is not None or args.fork_at is not None
                    or any(value is not None for value in onboarding_values)
                    or any(value is not None for value in comparison_values)
                    or args.mirror_attempts != 64 or args.practice_games != 0):
                raise FirstPlayableJourneyError("invalid quarantine inspection mode")
            receipt = inspect_offline_install_quarantine(
                args.output, args.archive,
                expected_archive_sha256=args.expected_archive_sha256,
                expected_manifest_sha256=args.expected_manifest_sha256,
                authorized=args.trusted_local_operator,
            )
        elif args.preflight_install:
            if (args.reconcile_install or args.check_archive_save
                    or args.install_archive or args.package_existing
                    or args.inspect_archive or args.play_existing or args.compare_saves
                    or args.verify_existing or args.reconcile_receipt
                    or args.inspect_receipt or args.onboard or args.migrate_progress
                    or args.preflight_migration or args.reconcile_migration
                    or args.output is None or args.archive is None
                    or args.expected_archive_sha256 is None
                    or args.expected_manifest_sha256 is None
                    or args.intent is not None or args.receipt is not None
                    or args.expected_receipt_sha256 is not None
                    or args.moves is not None or args.load_save is not None
                    or args.expected_save_sha256 is not None
                    or args.save is not None or args.fork_at is not None
                    or any(value is not None for value in onboarding_values)
                    or any(value is not None for value in comparison_values)
                    or args.mirror_attempts != 64 or args.practice_games != 0):
                raise FirstPlayableJourneyError("invalid offline install preflight mode")
            receipt = preflight_offline_game_install(
                args.archive, args.output,
                expected_archive_sha256=args.expected_archive_sha256,
                expected_manifest_sha256=args.expected_manifest_sha256,
                authorized=args.trusted_local_operator,
            )
        elif args.reconcile_install:
            if (args.preflight_install or args.check_archive_save or args.install_archive or args.package_existing
                    or args.inspect_archive or args.play_existing or args.compare_saves
                    or args.verify_existing or args.reconcile_receipt
                    or args.inspect_receipt or args.onboard or args.migrate_progress
                    or args.preflight_migration or args.reconcile_migration
                    or args.output is None or args.archive is None
                    or args.expected_archive_sha256 is None
                    or args.expected_manifest_sha256 is None
                    or args.intent is not None or args.receipt is not None
                    or args.expected_receipt_sha256 is not None
                    or args.moves is not None or args.load_save is not None
                    or args.expected_save_sha256 is not None
                    or args.save is not None or args.fork_at is not None
                    or any(value is not None for value in onboarding_values)
                    or any(value is not None for value in comparison_values)
                    or args.mirror_attempts != 64 or args.practice_games != 0):
                raise FirstPlayableJourneyError("invalid installed-source reconciliation mode")
            receipt = reconcile_installed_game_archive(
                args.output, args.archive,
                expected_archive_sha256=args.expected_archive_sha256,
                expected_manifest_sha256=args.expected_manifest_sha256,
                authorized=args.trusted_local_operator,
            )
        elif args.check_archive_save:
            if (args.preflight_migration or args.migrate_progress
                    or args.reconcile_migration or args.install_archive
                    or args.package_existing or args.inspect_archive
                    or args.play_existing or args.compare_saves
                    or args.verify_existing or args.reconcile_receipt
                    or args.inspect_receipt or args.onboard
                    or args.archive is None or args.load_save is None
                    or args.expected_archive_sha256 is None
                    or args.expected_manifest_sha256 is None
                    or args.expected_save_sha256 is None
                    or args.output is not None or args.save is not None
                    or args.intent is not None or args.receipt is not None
                    or args.expected_receipt_sha256 is not None
                    or any(value is not None for value in onboarding_values)
                    or any(value is not None for value in comparison_values)
                    or args.moves is not None or args.fork_at is not None
                    or args.mirror_attempts != 64 or args.practice_games != 0):
                raise FirstPlayableJourneyError("invalid archive/save replay check mode")
            raw_save = read_private_game_save(
                args.load_save, expected_sha256=args.expected_save_sha256,
                authorized=args.trusted_local_operator,
            )
            receipt = verify_archived_progress_binding(
                args.archive, raw_save,
                expected_archive_sha256=args.expected_archive_sha256,
                expected_manifest_sha256=args.expected_manifest_sha256,
                expected_save_sha256=args.expected_save_sha256,
                authorized=args.trusted_local_operator,
            )
        elif args.preflight_migration:
            if (args.migrate_progress or args.reconcile_migration
                    or args.install_archive or args.package_existing
                    or args.inspect_archive or args.play_existing or args.compare_saves
                    or args.verify_existing or args.reconcile_receipt
                    or args.inspect_receipt or args.onboard or args.output is None
                    or args.archive is None or args.expected_archive_sha256 is None
                    or args.expected_manifest_sha256 is None
                    or args.load_save is None or args.expected_save_sha256 is None
                    or args.save is None or args.intent is not None
                    or args.receipt is not None or args.expected_receipt_sha256 is not None
                    or any(value is not None for value in onboarding_values)
                    or any(value is not None for value in comparison_values)
                    or args.moves is not None or args.fork_at is not None
                    or args.mirror_attempts != 64 or args.practice_games != 0):
                raise FirstPlayableJourneyError("invalid offline migration preflight mode")
            receipt = preflight_offline_game_migration(
                args.archive, args.output,
                expected_archive_sha256=args.expected_archive_sha256,
                expected_manifest_sha256=args.expected_manifest_sha256,
                original_save=args.load_save,
                expected_save_sha256=args.expected_save_sha256,
                migrated_save=args.save,
                authorized=args.trusted_local_operator,
            )
        elif args.reconcile_migration:
            if (args.preflight_migration or args.migrate_progress or args.install_archive or args.package_existing
                    or args.inspect_archive or args.play_existing or args.compare_saves
                    or args.verify_existing or args.reconcile_receipt
                    or args.inspect_receipt or args.onboard or args.output is None
                    or args.load_save is None or args.expected_save_sha256 is None
                    or args.expected_manifest_sha256 is None
                    or (args.archive is None) != (args.expected_archive_sha256 is None)
                    or args.intent is not None or args.receipt is not None
                    or args.expected_receipt_sha256 is not None
                    or any(value is not None for value in onboarding_values)
                    or any(value is not None for value in comparison_values)
                    or args.moves is not None or args.save is not None
                    or args.fork_at is not None or args.mirror_attempts != 64
                    or args.practice_games != 0):
                raise FirstPlayableJourneyError("invalid offline progress reconciliation mode")
            receipt = reconcile_migrated_offline_progress(
                args.output, args.load_save,
                expected_manifest_sha256=args.expected_manifest_sha256,
                expected_save_sha256=args.expected_save_sha256,
                archive=args.archive,
                expected_archive_sha256=args.expected_archive_sha256,
                authorized=args.trusted_local_operator,
            )
        elif args.migrate_progress:
            if (args.preflight_migration or args.install_archive or args.package_existing or args.inspect_archive
                    or args.play_existing or args.compare_saves or args.verify_existing
                    or args.reconcile_receipt or args.inspect_receipt or args.onboard
                    or args.output is None or args.archive is None
                    or args.expected_manifest_sha256 is None
                    or args.expected_archive_sha256 is None
                    or args.load_save is None or args.expected_save_sha256 is None
                    or args.save is None or args.intent is not None
                    or args.receipt is not None or args.expected_receipt_sha256 is not None
                    or any(value is not None for value in onboarding_values)
                    or any(value is not None for value in comparison_values)
                    or args.moves is not None or args.fork_at is not None
                    or args.mirror_attempts != 64 or args.practice_games != 0):
                raise FirstPlayableJourneyError("invalid offline progress migration mode")
            receipt = migrate_offline_game_progress(
                args.archive, args.output,
                expected_archive_sha256=args.expected_archive_sha256,
                expected_manifest_sha256=args.expected_manifest_sha256,
                original_save=args.load_save,
                expected_save_sha256=args.expected_save_sha256,
                migrated_save=args.save,
                authorized=args.trusted_local_operator,
            )
        elif args.install_archive:
            if (args.package_existing or args.inspect_archive or args.play_existing
                    or args.compare_saves or args.verify_existing
                    or args.reconcile_receipt or args.inspect_receipt or args.onboard
                    or args.output is None or args.archive is None
                    or args.expected_manifest_sha256 is None
                    or args.expected_archive_sha256 is None
                    or args.intent is not None or args.receipt is not None
                    or args.expected_receipt_sha256 is not None
                    or any(value is not None for value in onboarding_values)
                    or any(value is not None for value in comparison_values)
                    or args.moves is not None or args.load_save is not None
                    or args.expected_save_sha256 is not None or args.save is not None
                    or args.fork_at is not None or args.mirror_attempts != 64
                    or args.practice_games != 0):
                raise FirstPlayableJourneyError("invalid offline archive install mode")
            receipt = install_offline_game_source(
                args.archive, args.output,
                expected_archive_sha256=args.expected_archive_sha256,
                expected_manifest_sha256=args.expected_manifest_sha256,
                authorized=args.trusted_local_operator,
            )
        elif args.package_existing or args.inspect_archive:
            if (args.package_existing == args.inspect_archive
                    or args.archive is None or args.expected_manifest_sha256 is None
                    or args.onboard or args.play_existing or args.compare_saves
                    or args.verify_existing or args.reconcile_receipt or args.inspect_receipt
                    or args.intent is not None or args.receipt is not None
                    or args.expected_receipt_sha256 is not None
                    or any(value is not None for value in onboarding_values)
                    or any(value is not None for value in comparison_values)
                    or args.moves is not None or args.load_save is not None
                    or args.expected_save_sha256 is not None or args.save is not None
                    or args.fork_at is not None or args.mirror_attempts != 64
                    or args.practice_games != 0):
                raise FirstPlayableJourneyError("invalid offline archive mode")
            if args.package_existing:
                if args.output is None or args.expected_archive_sha256 is not None:
                    raise FirstPlayableJourneyError("package requires source and no archive pin")
                receipt = publish_offline_game_archive(
                    args.output, args.archive,
                    expected_manifest_sha256=args.expected_manifest_sha256,
                    authorized=args.trusted_local_operator,
                )
            else:
                if args.output is not None or args.expected_archive_sha256 is None:
                    raise FirstPlayableJourneyError("inspection requires archive and both pins")
                receipt = inspect_offline_game_archive(
                    args.archive, expected_archive_sha256=args.expected_archive_sha256,
                    expected_manifest_sha256=args.expected_manifest_sha256,
                    authorized=args.trusted_local_operator,
                )
        elif args.archive is not None or args.expected_archive_sha256 is not None:
            raise FirstPlayableJourneyError("archive options require explicit archive mode")
        elif args.compare_saves:
            if (args.play_existing or args.reconcile_receipt or args.inspect_receipt
                    or args.verify_existing or args.onboard or args.intent is not None
                    or args.output is None or args.expected_manifest_sha256 is None
                    or any(value is None for value in comparison_values)
                    or any(value is not None for value in onboarding_values)
                    or args.receipt is not None or args.expected_receipt_sha256 is not None
                    or args.moves is not None or args.load_save is not None
                    or args.expected_save_sha256 is not None or args.save is not None
                    or args.fork_at is not None or args.mirror_attempts != 64
                    or args.practice_games != 0):
                raise FirstPlayableJourneyError("invalid offline save comparison mode")
            receipt = compare_verified_offline_saves(
                args.output, expected_manifest_sha256=args.expected_manifest_sha256,
                left_save=args.left_save, left_sha256=args.left_sha256,
                right_save=args.right_save, right_sha256=args.right_sha256,
                authorized=args.trusted_local_operator,
            )
        elif any(value is not None for value in comparison_values):
            raise FirstPlayableJourneyError("save comparison options require --compare-saves")
        elif args.play_existing:
            if (args.reconcile_receipt or args.inspect_receipt or args.verify_existing
                    or args.onboard or args.output is None
                    or args.expected_manifest_sha256 is None
                    or args.expected_receipt_sha256 is not None
                    or args.receipt is not None or args.intent is not None
                    or any(value is not None for value in onboarding_values)
                    or args.mirror_attempts != 64 or args.practice_games != 0):
                raise FirstPlayableJourneyError("invalid offline gameplay mode")
            receipt = play_existing_source_game(
                args.output, expected_manifest_sha256=args.expected_manifest_sha256,
                authorized=args.trusted_local_operator,
                moves=_parse_moves(args.moves),
                load_save=args.load_save,
                expected_save_sha256=args.expected_save_sha256,
                save_destination=args.save,
                fork_at_step=args.fork_at,
            )
        elif args.reconcile_receipt:
            if args.moves is not None or args.load_save is not None or args.save is not None or args.expected_save_sha256 is not None or args.fork_at is not None:
                raise FirstPlayableJourneyError("offline gameplay options require --play-existing")
            if (args.inspect_receipt or args.verify_existing or args.onboard
                    or args.output is None or args.receipt is None
                    or args.expected_manifest_sha256 is None
                    or args.expected_receipt_sha256 is None
                    or args.intent is not None
                    or any(value is not None for value in onboarding_values)
                    or args.mirror_attempts != 64 or args.practice_games != 0):
                raise FirstPlayableJourneyError("invalid source/receipt reconciliation mode")
            receipt = reconcile_first_playable_receipt(
                args.output, args.receipt,
                expected_manifest_sha256=args.expected_manifest_sha256,
                expected_receipt_sha256=args.expected_receipt_sha256,
                authorized=args.trusted_local_operator,
            )
        elif args.inspect_receipt:
            if args.moves is not None or args.load_save is not None or args.save is not None or args.expected_save_sha256 is not None or args.fork_at is not None:
                raise FirstPlayableJourneyError("offline gameplay options require --play-existing")
            if (args.play_existing or args.reconcile_receipt or args.verify_existing or args.onboard or args.output is not None
                    or any(value is not None for value in onboarding_values)
                    or args.intent is not None or args.expected_manifest_sha256 is not None
                    or args.receipt is None or args.expected_receipt_sha256 is None
                    or args.mirror_attempts != 64 or args.practice_games != 0):
                raise FirstPlayableJourneyError("invalid archived receipt inspection mode")
            receipt = inspect_first_playable_receipt(
                args.receipt, expected_sha256=args.expected_receipt_sha256,
                authorized=args.trusted_local_operator,
            )
        elif args.verify_existing:
            if args.moves is not None or args.load_save is not None or args.save is not None or args.expected_save_sha256 is not None or args.fork_at is not None:
                raise FirstPlayableJourneyError("offline gameplay options require --play-existing")
            if (args.play_existing or args.reconcile_receipt or args.output is None or args.intent is not None or args.onboard
                    or any(value is not None for value in onboarding_values)
                    or args.expected_receipt_sha256 is not None
                    or args.mirror_attempts != 64 or args.practice_games != 0):
                raise FirstPlayableJourneyError(
                    "existing verification cannot build or tune a new game"
                )
            receipt = verify_existing_playable_journey(
                args.output, expected_manifest_sha256=args.expected_manifest_sha256,
                authorized=args.trusted_local_operator,
                receipt_destination=args.receipt,
            )
        else:
            if args.moves is not None or args.load_save is not None or args.save is not None or args.expected_save_sha256 is not None or args.fork_at is not None:
                raise FirstPlayableJourneyError("offline gameplay options require --play-existing")
            if (args.play_existing or args.reconcile_receipt or args.output is None or args.expected_manifest_sha256 is not None
                    or args.expected_receipt_sha256 is not None):
                raise FirstPlayableJourneyError(
                    "new game builds require --output and reject verification pins"
                )
            if args.onboard:
                if (args.intent is not None or args.project_id is None
                        or args.title is None or args.seed is None):
                    raise FirstPlayableJourneyError(
                        "onboarding requires --project-id, --title, --seed and no --intent"
                    )
                source_intent = GameBuildIntent(
                    project_id=args.project_id, title=args.title,
                    subtitle=(args.subtitle if args.subtitle is not None
                              else "An original offline adventure"),
                    seed=args.seed,
                    theme=args.theme if args.theme is not None else "forest",
                    width=args.width if args.width is not None else 9,
                    height=args.height if args.height is not None else 9,
                    levels=args.levels if args.levels is not None else 1,
                    collectibles_per_level=1, hazards_per_level=0,
                    starting_health=3,
                )
            else:
                if (args.intent is None
                        or any(value is not None for value in onboarding_values)):
                    raise FirstPlayableJourneyError(
                        "JSON builds require --intent and reject onboarding options"
                    )
                source_intent = args.intent
            receipt = build_first_playable_journey(
                source_intent, args.output,
                authorized=args.trusted_local_operator,
                mirror_attempts=args.mirror_attempts,
                practice_games=args.practice_games,
                receipt_destination=args.receipt,
                expected_intent_sha256=args.expected_intent_sha256,
            )
    except (
        FirstPlayableJourneyError, PrivateGameSaveError, OfflineSaveComparisonError,
        OfflineGameArchiveError, OfflineSourceInstallError,
        OfflineInstallReconciliationError, OfflineInstallQuarantineError,
        OfflineProgressMigrationError, OfflineProgressReconciliationError,
        StudioError, PlayableWorldError,
        PlayableCompilationError, GameplayError, MirrorRoomError,
        ToolFabricError, DualRuntimeExportError, DualRuntimeVerificationError,
        ReceiptPublicationError, ReceiptInspectionError,
        AtomicDirectoryPublicationError,
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


__all__ = [
    "SCHEMA", "VERIFY_SCHEMA", "INSPECT_SCHEMA", "RECONCILE_SCHEMA", "PLAY_SCHEMA", "FirstPlayableJourneyError",
    "build_first_playable_journey", "verify_existing_playable_journey",
    "inspect_first_playable_receipt", "reconcile_first_playable_receipt",
    "play_existing_source_game", "main",
]
