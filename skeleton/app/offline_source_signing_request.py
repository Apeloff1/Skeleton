"""Produce a deterministic, independently pinned offline-source signing request.

This is a read-only bridge between a verified original game archive and an
external Ed25519 signing authority. It does not load a private key, issue a
signature, approve rights, or certify a native package/device for consumers.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Sequence

from skeleton.app.offline_archive_signature import (
    _pin, source_archive_signature_message,
)
from skeleton.app.offline_delivery_archive import inspect_offline_game_archive
from skeleton.app.offline_progress_compatibility import _archive_identity

SCHEMA = "skeleton.app.offline_source_signing_request.v1"


class OfflineSourceSigningRequestError(ValueError):
    """Pinned original source could not be admitted for external signing."""


def prepare_offline_source_signing_request(
    archive: str | Path, *,
    expected_archive_sha256: str,
    expected_manifest_sha256: str,
    authorized: bool,
) -> dict[str, object]:
    """Verify original source twice and return exact domain-separated bytes.

    The archive/manifest SHA-256 pins must be supplied independently. The
    returned message is suitable for a separately controlled Ed25519 signer,
    but its presence is never evidence that signing or release occurred.
    """
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    _pin(expected_archive_sha256, "archive")
    _pin(expected_manifest_sha256, "manifest")
    original = _archive_identity(archive)
    before = inspect_offline_game_archive(
        archive, expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256, authorized=True,
    )
    message = source_archive_signature_message(
        expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
    )
    after = inspect_offline_game_archive(
        archive, expected_archive_sha256=expected_archive_sha256,
        expected_manifest_sha256=expected_manifest_sha256, authorized=True,
    )
    if (
        original != _archive_identity(archive)
        or before != after
        or after.get("archive_integrity_verified") is not True
        or after.get("archive_sha256") != expected_archive_sha256
        or after.get("manifest_sha256") != expected_manifest_sha256
        or after.get("release_certified") is not False
    ):
        raise OfflineSourceSigningRequestError(
            "original source changed during external signing request preparation"
        )
    return {
        "schema": SCHEMA,
        "status": "verified_source_signing_request_unsigned_release_blocked",
        "archive_sha256": expected_archive_sha256,
        "manifest_sha256": expected_manifest_sha256,
        "archived_files": after["archived_files"],
        "signature_algorithm_requested": "Ed25519",
        "signature_message_encoding": "hex",
        "signature_message_hex": message.hex(),
        "signature_message_sha256": sha256(message).hexdigest(),
        "source_archive_integrity_verified": True,
        "signature_issued": False,
        "private_signing_key_loaded": False,
        "native_executable_package_signed": False,
        "native_device_qualified": False,
        "publisher_identity_certified": False,
        "rights_certified": False,
        "package_signed": False,
        "release_certified": False,
        "read_only": True,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton app source-signing-request",
        description="Read-only verified original source Ed25519 signing request",
    )
    parser.add_argument("--archive", required=True)
    parser.add_argument("--expected-archive-sha256", required=True)
    parser.add_argument("--expected-manifest-sha256", required=True)
    parser.add_argument("--trusted-local-operator", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = prepare_offline_source_signing_request(
            args.archive,
            expected_archive_sha256=args.expected_archive_sha256,
            expected_manifest_sha256=args.expected_manifest_sha256,
            authorized=args.trusted_local_operator,
        )
    except (PermissionError, OSError, ValueError, TypeError) as exc:
        print(json.dumps({
            "schema": SCHEMA, "status": "blocked",
            "error": type(exc).__name__, "release_certified": False,
        }, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


__all__ = [
    "SCHEMA", "OfflineSourceSigningRequestError",
    "prepare_offline_source_signing_request", "main",
]
