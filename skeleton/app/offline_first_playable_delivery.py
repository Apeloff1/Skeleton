"""End-to-end original game delivery acceptance, with independent replay custody.

This command exercises actual exported source -> ZIP -> fresh installation ->
interactive moves -> private save -> restored play -> independent delivery
assurance. It is a POSIX source-level acceptance path, NOT native-device,
rights, signing, malware, marketplace or consumer-release qualification.
"""
from __future__ import annotations

import argparse
import hmac
import json
import os
from pathlib import Path
import sys
from typing import Sequence

from skeleton.ai.game_builder.dual_runtime_verify import (
    _canonical_bytes, _json, verify_exported_package,
)
from skeleton.ai.game_builder.offline_receipt_publication import (
    preflight_receipt_destination, publish_verified_receipt,
)
from skeleton.app.offline_archive_install import (
    _parent as _install_parent, install_offline_game_source,
    preflight_offline_game_install,
)
from skeleton.app.offline_delivery_archive import (
    _parent as _archive_parent, publish_offline_game_archive,
)
from skeleton.app.offline_delivery_assurance import (
    _archive_identity, _save_identity, _source_identity, _pin,
    assure_offline_delivery,
)
from skeleton.app.private_game_save import read_private_game_save
from skeleton.app.studio_journey import play_existing_source_game

SCHEMA = "skeleton.app.first_playable_delivery_acceptance.v1"
MAX_ACTIONS = 64
MAX_RECEIPT_BYTES = 256 * 1024
_ACTIONS = frozenset(("up", "down", "left", "right"))


class FirstPlayableDeliveryAcceptanceError(ValueError):
    """A live, source-bound install/play/save/delivery contract did not hold."""


def _path(value: str | Path) -> Path:
    """Normalize lexical dot segments before source/output overlap checks.

    Path.absolute() retains '..' on supported Python versions. That allowed
    a descriptor-safe but lexically disguised output to live inside the
    original game source tree when an existing sibling/.. was supplied.
    Do not resolve symlinks: the descriptor-anchored openers must reject them.
    """
    return Path(os.path.abspath(os.fspath(Path(value).expanduser())))


def _is_within(child: Path, root: Path) -> bool:
    return child == root or root in child.parents


def _unused(target: Path, opener) -> None:
    """Reject an occupied name through its nofollow, owner-controlled parent."""
    _, parent_fd = opener(target)
    try:
        try:
            os.stat(target.name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            return
        raise FirstPlayableDeliveryAcceptanceError(
            "delivery destination is already occupied; no overwrite permitted"
        )
    finally:
        os.close(parent_fd)


def _preflight(
    source: Path, archive: Path, install: Path, save: Path, receipt: Path,
    *, expected_manifest_sha256: str, authorized: bool,
) -> dict[str, object]:
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    _pin(expected_manifest_sha256, "manifest")
    targets = (archive, install, save, receipt)
    if len(set(targets)) != 4:
        raise FirstPlayableDeliveryAcceptanceError("delivery output names overlap")
    if _is_within(install, source) or _is_within(source, install):
        raise FirstPlayableDeliveryAcceptanceError(
            "fresh installation must be disjoint from original source"
        )
    if any(_is_within(target, source) or _is_within(target, install)
           for target in (archive, save, receipt)):
        raise FirstPlayableDeliveryAcceptanceError(
            "archive, save and receipt must remain outside both game trees"
        )
    _unused(archive, _archive_parent)
    _unused(install, _install_parent)
    preflight_receipt_destination(
        save, protected_roots=(source, install), authorized=True,
    )
    preflight_receipt_destination(
        receipt, protected_roots=(source, install), authorized=True,
    )
    # Byte-identical directory replacement is still a custody change. Bind
    # the original source root across BOTH independent verifier passes, not
    # only after admission returns to the publisher.
    source_identity = _source_identity(source)
    before = verify_exported_package(
        source, expected_manifest_sha256=expected_manifest_sha256,
        authorized=True,
    )
    if _source_identity(source) != source_identity:
        raise FirstPlayableDeliveryAcceptanceError(
            "original source root changed during first admission replay"
        )
    after = verify_exported_package(
        source, expected_manifest_sha256=expected_manifest_sha256,
        authorized=True,
    )
    if _source_identity(source) != source_identity:
        raise FirstPlayableDeliveryAcceptanceError(
            "original source root changed during second admission replay"
        )
    if before != after or before.get("offline_gameplay_reexecuted") is not True:
        raise FirstPlayableDeliveryAcceptanceError(
            "original source changed or did not replay during admission"
        )
    if before.get("release_certified") is not False:
        raise FirstPlayableDeliveryAcceptanceError(
            "source verifier made an unsupported release claim"
        )
    return before


def _envelope(assurance: dict[str, object]) -> dict[str, object]:
    if (type(assurance) is not dict
            or assurance.get("schema") != "skeleton.app.offline_delivery_assurance.v1"
            or assurance.get("offline_gameplay_reexecuted") is not True
            or assurance.get("release_certified") is not False
            or assurance.get("installed_source_archive_binding_verified") is not True
            or assurance.get("private_save_world_binding_verified") is not True):
        raise FirstPlayableDeliveryAcceptanceError(
            "canonical delivery assurance did not qualify"
        )
    fields = (
        "project_id", "manifest_sha256", "archive_sha256", "save_sha256",
        "world_digest", "replay_digest", "action_count", "installed_files",
    )
    if any(key not in assurance for key in fields):
        raise FirstPlayableDeliveryAcceptanceError(
            "canonical assurance omitted a required identity"
        )
    return {
        "schema": SCHEMA,
        **{key: assurance[key] for key in fields},
        "offline_gameplay_reexecuted": True,
        "installed_source_archive_binding_verified": True,
        "private_save_world_binding_verified": True,
        "independent_pin_distribution_required": True,
        "source_level_replay_evidence": True,
        "native_device_qualified": False,
        "model_inference_observed": False,
        "package_signed": False,
        "rights_certified": False,
        "release_certified": False,
        "persistent_rollback_protection": False,
    }


def _read_receipt(receipt: Path, expected_sha256: str) -> dict[str, object]:
    _pin(expected_sha256, "receipt")
    raw = read_private_game_save(
        receipt, expected_sha256=expected_sha256, authorized=True,
    )
    if not 0 < len(raw) <= MAX_RECEIPT_BYTES:
        raise FirstPlayableDeliveryAcceptanceError("receipt byte budget exceeded")
    stored = _json(raw, MAX_RECEIPT_BYTES)
    if (type(stored) is not dict
            or stored.get("schema") != SCHEMA
            or not hmac.compare_digest(raw, _canonical_bytes(stored))
            or stored.get("release_certified") is not False
            or stored.get("native_device_qualified") is not False
            or stored.get("rights_certified") is not False):
        raise FirstPlayableDeliveryAcceptanceError(
            "private delivery evidence is not canonical or supported"
        )
    return stored


def _assure(
    install: Path, archive: Path, save: Path, *,
    expected_manifest_sha256: str,
    expected_archive_sha256: str,
    expected_save_sha256: str,
) -> dict[str, object]:
    return assure_offline_delivery(
        install, archive, save,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_archive_sha256=expected_archive_sha256,
        expected_save_sha256=expected_save_sha256,
        authorized=True,
    )


def publish_first_playable_delivery(
    source: str | Path, archive: str | Path, install: str | Path,
    save: str | Path, receipt: str | Path, *,
    expected_manifest_sha256: str, moves: Sequence[str],
    authorized: bool,
) -> dict[str, object]:
    """Publish a fresh delivery only after genuine gameplay and restored replay.

    Every destination is checked before the first write, then rechecked at
    its own atomic no-clobber publication boundary. Failures after publication
    preserve any published outputs for quarantine, never pathname rollback.
    """
    if (type(moves) not in (tuple, list)
            or not 1 <= len(moves) <= MAX_ACTIONS
            or any(type(action) is not str or action not in _ACTIONS
                   for action in moves)):
        raise FirstPlayableDeliveryAcceptanceError(
            "1-64 bounded original player moves required"
        )
    source, archive, install, save, receipt = map(
        _path, (source, archive, install, save, receipt),
    )
    source_verified = _preflight(
        source, archive, install, save, receipt,
        expected_manifest_sha256=expected_manifest_sha256,
        authorized=authorized,
    )
    original_source_identity = _source_identity(source)
    published = publish_offline_game_archive(
        source, archive, expected_manifest_sha256=expected_manifest_sha256,
        authorized=True,
    )
    archive_pin = published["independent_archive_sha256"]
    # ZIP publication is irreversible and can take time. A source swap during
    # that step must stop BEFORE the fresh installer writes another artifact.
    # Keep the published ZIP for explicit quarantine; never pathname rollback.
    if (original_source_identity != _source_identity(source)
            or source_verified != verify_exported_package(
                source, expected_manifest_sha256=expected_manifest_sha256,
                authorized=True,
            )):
        raise FirstPlayableDeliveryAcceptanceError(
            "original source changed during archive publication; install blocked"
        )
    admitted = preflight_offline_game_install(
        archive, install, expected_archive_sha256=archive_pin,
        expected_manifest_sha256=expected_manifest_sha256, authorized=True,
    )
    if admitted.get("destination_reserved") is not False:
        raise FirstPlayableDeliveryAcceptanceError(
            "preflight unexpectedly claimed an installation reservation"
        )
    installed = install_offline_game_source(
        archive, install, expected_archive_sha256=archive_pin,
        expected_manifest_sha256=expected_manifest_sha256, authorized=True,
    )
    if (installed.get("world_digest") != source_verified.get("world_digest")
            or installed.get("project_id") != source_verified.get("project_id")
            or installed.get("source_installation_verified") is not True):
        raise FirstPlayableDeliveryAcceptanceError(
            "fresh installed game differs from independently verified source"
        )
    played = play_existing_source_game(
        install, expected_manifest_sha256=expected_manifest_sha256,
        authorized=True, moves=moves, save_destination=save,
    )
    save_pin = played["independent_save_sha256"]
    restored = play_existing_source_game(
        install, expected_manifest_sha256=expected_manifest_sha256,
        authorized=True, moves=(), load_save=save,
        expected_save_sha256=save_pin,
    )
    if (restored.get("replay_digest") != played.get("replay_digest")
            or restored.get("action_count") != len(moves)
            or restored.get("final_state") != played.get("final_state")
            or restored.get("independent_save_sha256") is not None
            or restored.get("world_digest") != installed.get("world_digest")):
        raise FirstPlayableDeliveryAcceptanceError(
            "restored original player actions do not reproduce the saved game"
        )
    custody_before = (
        _source_identity(install), _archive_identity(archive),
        _save_identity(save),
    )
    assurance = _assure(
        install, archive, save,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_archive_sha256=archive_pin, expected_save_sha256=save_pin,
    )
    envelope = _envelope(assurance)
    if (envelope["replay_digest"] != played["replay_digest"]
            or envelope["action_count"] != len(moves)
            or envelope["world_digest"] != installed["world_digest"]):
        raise FirstPlayableDeliveryAcceptanceError(
            "final delivery assurance differs from interactive replay"
        )
    receipt_pin = publish_verified_receipt(
        envelope, receipt, protected_roots=(source, install),
        authorized=True,
    )
    if (original_source_identity != _source_identity(source)
            or source_verified != verify_exported_package(
                source, expected_manifest_sha256=expected_manifest_sha256,
                authorized=True,
            )
            or _read_receipt(receipt, receipt_pin) != envelope
            or assurance != _assure(
                install, archive, save,
                expected_manifest_sha256=expected_manifest_sha256,
                expected_archive_sha256=archive_pin, expected_save_sha256=save_pin,
            )
            or custody_before != (
                _source_identity(install), _archive_identity(archive),
                _save_identity(save),
            )):
        raise FirstPlayableDeliveryAcceptanceError(
            "published receipt or live delivery changed after publication"
        )
    return {
        "schema": SCHEMA,
        "status": "fresh_original_game_delivered_replayed_release_blocked",
        "source_directory": str(source),
        "archive_file": str(archive),
        "install_directory": str(install),
        "private_save_file": str(save),
        "receipt_file": str(receipt),
        "independent_receipt_sha256": receipt_pin,
        **envelope,
    }


def inspect_first_playable_delivery(
    install: str | Path, archive: str | Path, save: str | Path,
    receipt: str | Path, *, expected_manifest_sha256: str,
    expected_archive_sha256: str, expected_save_sha256: str,
    expected_receipt_sha256: str, authorized: bool,
) -> dict[str, object]:
    """Reexecute live delivered game against FOUR externally retained pins."""
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    install, archive, save, receipt = map(
        _path, (install, archive, save, receipt),
    )
    if len({install, archive, save, receipt}) != 4 or any(
        _is_within(path, install) for path in (archive, save, receipt)
    ):
        raise FirstPlayableDeliveryAcceptanceError(
            "delivery evidence overlaps the installed game tree"
        )
    for pin, name in (
        (expected_manifest_sha256, "manifest"),
        (expected_archive_sha256, "archive"),
        (expected_save_sha256, "save"),
        (expected_receipt_sha256, "receipt"),
    ):
        _pin(pin, name)
    custody_before = (
        _source_identity(install), _archive_identity(archive),
        _save_identity(save), _save_identity(receipt),
    )
    stored = _read_receipt(receipt, expected_receipt_sha256)
    assurance = _assure(
        install, archive, save,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_archive_sha256=expected_archive_sha256,
        expected_save_sha256=expected_save_sha256,
    )
    if (stored != _envelope(assurance)
            or stored != _read_receipt(receipt, expected_receipt_sha256)
            or assurance != _assure(
                install, archive, save,
                expected_manifest_sha256=expected_manifest_sha256,
                expected_archive_sha256=expected_archive_sha256,
                expected_save_sha256=expected_save_sha256,
            )
            or custody_before != (
                _source_identity(install), _archive_identity(archive),
                _save_identity(save), _save_identity(receipt),
            )):
        raise FirstPlayableDeliveryAcceptanceError(
            "pinned receipt, game, archive or private replay diverged"
        )
    return {
        **stored,
        "status": "live_original_game_delivery_reverified_release_blocked",
        "independent_receipt_sha256": expected_receipt_sha256,
        "receipt_integrity_verified": True,
        "independent_pin_reverified": True,
        "live_source_and_private_replay_reexecuted": True,
        "read_only": True,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton app first-playable-delivery",
        description="Exercise original source -> archive -> install -> play -> save -> restore -> delivery assurance",
    )
    parser.add_argument("--source")
    parser.add_argument("--archive", required=True)
    parser.add_argument("--install", required=True)
    parser.add_argument("--save", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--expected-manifest-sha256", required=True)
    parser.add_argument("--moves", help="1-64 comma-separated up/down/left/right player moves")
    parser.add_argument("--inspect", action="store_true", help="read-only live re-verification of published delivery")
    parser.add_argument("--expected-archive-sha256")
    parser.add_argument("--expected-save-sha256")
    parser.add_argument("--expected-receipt-sha256")
    parser.add_argument("--trusted-local-operator", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.inspect:
            if (args.source is not None or args.moves is not None
                    or not all((args.expected_archive_sha256,
                                args.expected_save_sha256,
                                args.expected_receipt_sha256))):
                raise FirstPlayableDeliveryAcceptanceError(
                    "inspection requires three additional independent pins and no build inputs"
                )
            result = inspect_first_playable_delivery(
                args.install, args.archive, args.save, args.receipt,
                expected_manifest_sha256=args.expected_manifest_sha256,
                expected_archive_sha256=args.expected_archive_sha256,
                expected_save_sha256=args.expected_save_sha256,
                expected_receipt_sha256=args.expected_receipt_sha256,
                authorized=args.trusted_local_operator,
            )
        else:
            if (args.source is None or args.moves is None
                    or any((args.expected_archive_sha256,
                            args.expected_save_sha256,
                            args.expected_receipt_sha256))):
                raise FirstPlayableDeliveryAcceptanceError(
                    "publication requires original source and moves, never output pins"
                )
            actions = tuple(args.moves.split(","))
            result = publish_first_playable_delivery(
                args.source, args.archive, args.install, args.save, args.receipt,
                expected_manifest_sha256=args.expected_manifest_sha256,
                moves=actions, authorized=args.trusted_local_operator,
            )
    except (PermissionError, OSError, TypeError, ValueError, RuntimeError) as exc:
        print(json.dumps({
            "schema": SCHEMA, "status": "blocked",
            "error": type(exc).__name__, "release_certified": False,
        }, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "SCHEMA", "FirstPlayableDeliveryAcceptanceError",
    "publish_first_playable_delivery", "inspect_first_playable_delivery", "main",
]
