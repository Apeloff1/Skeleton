"""Read-only signed original-game delivery plus installed gameplay/save acceptance.

A detached signature alone is not an installation proof. A replay receipt alone
is not a signature. This gate requires both, with stable source/key/save inodes.
No native executable package or consumer device is certified by this operation.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from skeleton.app.offline_archive_signature import (
    _pin, _read_detached_file, verify_offline_source_archive_signature,
)
from skeleton.app.offline_delivery_assurance import (
    _save_identity, _source_identity, assure_offline_delivery,
)
from skeleton.app.offline_progress_compatibility import _archive_identity

SCHEMA = "skeleton.app.signed_offline_delivery_assurance.v1"


class SignedOfflineDeliveryError(ValueError):
    """Cross-custody source signature or gameplay replay did not qualify."""


def _identities(
    installed: str | Path, archive: str | Path, save: str | Path,
    key: str | Path, signature: str | Path,
) -> tuple[object, ...]:
    return (
        _source_identity(installed),
        _archive_identity(archive),
        _save_identity(save),
        _read_detached_file(key, length=32)[1],
        _read_detached_file(signature, length=64)[1],
    )


def assure_signed_offline_delivery(
    installed_source: str | Path, archive: str | Path,
    private_save: str | Path, public_key_file: str | Path,
    signature_file: str | Path, *,
    expected_archive_sha256: str,
    expected_manifest_sha256: str,
    expected_save_sha256: str,
    expected_public_key_sha256: str,
    authorized: bool,
) -> dict[str, object]:
    """Bind original ZIP signature to real installed source and saved actions."""
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    # Reject malformed external trust pins before reading any filesystem input.
    for name, value in (
        ("archive", expected_archive_sha256),
        ("manifest", expected_manifest_sha256),
        ("save", expected_save_sha256),
        ("public key", expected_public_key_sha256),
    ):
        _pin(value, name)
    before = _identities(
        installed_source, archive, private_save, public_key_file, signature_file,
    )
    signature = verify_offline_source_archive_signature(
        archive, public_key_file, signature_file,
        expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_public_key_sha256=expected_public_key_sha256,
        authorized=True,
    )
    delivery = assure_offline_delivery(
        installed_source, archive, private_save,
        expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_save_sha256=expected_save_sha256,
        authorized=True,
    )
    signature_after = verify_offline_source_archive_signature(
        archive, public_key_file, signature_file,
        expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_public_key_sha256=expected_public_key_sha256,
        authorized=True,
    )
    if (before != _identities(
            installed_source, archive, private_save, public_key_file,
            signature_file,
        ) or signature != signature_after
            or signature.get("source_archive_signature_verified") is not True
            or signature.get("source_archive_integrity_verified") is not True
            or delivery.get("installed_source_archive_binding_verified") is not True
            or delivery.get("private_save_world_binding_verified") is not True
            or delivery.get("offline_gameplay_reexecuted") is not True
            or signature.get("archive_sha256") != delivery.get("archive_sha256")
            or signature.get("manifest_sha256") != delivery.get("manifest_sha256")
            or signature.get("release_certified") is not False
            or delivery.get("release_certified") is not False):
        raise SignedOfflineDeliveryError(
            "source signature and installed playable custody disagree"
        )
    return {
        "schema": SCHEMA,
        "status": "signed_source_installed_playable_replay_verified_release_blocked",
        "project_id": delivery["project_id"],
        "archive_sha256": delivery["archive_sha256"],
        "manifest_sha256": delivery["manifest_sha256"],
        "save_sha256": delivery["save_sha256"],
        "public_key_sha256": signature["public_key_sha256"],
        "signed_message_sha256": signature["signed_message_sha256"],
        "world_digest": delivery["world_digest"],
        "replay_digest": delivery["replay_digest"],
        "action_count": delivery["action_count"],
        "source_archive_signature_verified": True,
        "installed_source_archive_binding_verified": True,
        "private_save_world_binding_verified": True,
        "offline_gameplay_reexecuted": True,
        "read_only": True,
        "native_executable_package_signed": False,
        "native_device_qualified": False,
        "rights_certified": False,
        "publisher_identity_certified": False,
        "package_signed": False,
        "release_certified": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton app signed-delivery-assurance",
        description="Read-only signed source + installed gameplay + private save verification",
    )
    parser.add_argument("--installed", required=True)
    parser.add_argument("--archive", required=True)
    parser.add_argument("--save", required=True)
    parser.add_argument("--public-key", required=True)
    parser.add_argument("--signature", required=True)
    parser.add_argument("--expected-archive-sha256", required=True)
    parser.add_argument("--expected-manifest-sha256", required=True)
    parser.add_argument("--expected-save-sha256", required=True)
    parser.add_argument("--expected-public-key-sha256", required=True)
    parser.add_argument("--trusted-local-operator", action="store_true")
    args = parser.parse_args(argv)
    try:
        receipt = assure_signed_offline_delivery(
            args.installed, args.archive, args.save,
            args.public_key, args.signature,
            expected_archive_sha256=args.expected_archive_sha256,
            expected_manifest_sha256=args.expected_manifest_sha256,
            expected_save_sha256=args.expected_save_sha256,
            expected_public_key_sha256=args.expected_public_key_sha256,
            authorized=args.trusted_local_operator,
        )
    except (PermissionError, OSError, ValueError, TypeError) as exc:
        print(json.dumps({
            "schema": SCHEMA, "status": "blocked",
            "error": type(exc).__name__, "release_certified": False,
        }, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


__all__ = [
    "SCHEMA", "SignedOfflineDeliveryError", "assure_signed_offline_delivery", "main",
]
