"""Read-only quarantine triage after an uncertain offline receipt publication.

An observable final name may survive a post-link fsync/identity failure. The
operator must independently pin its expected SHA-256 before inspection. This
tool never repairs, deletes, signs, approves, or replays the original game.
The canonical handoff inspector remains mandatory for game replay assurance.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import hmac
import json
from pathlib import Path
import re
import sys
from typing import Sequence

from skeleton.ai.game_builder.dual_runtime_verify import _canonical_bytes
from skeleton.app.offline_delivery_assurance import _save_identity
from skeleton.app.offline_mixed_game_library_continuity_handoff import (
    _reject_protected_receipt,
)
from skeleton.app.offline_mixed_game_library_handoff import (
    MAX_RECEIPT_BYTES, _read_envelope,
)

SCHEMA = "skeleton.app.offline_uncertain_receipt_inspection.v1"
_PIN = re.compile(r"[0-9a-f]{64}\Z")
_ALLOWED = frozenset({
    "skeleton.app.offline_mixed_game_library_handoff.v1",
    "skeleton.app.offline_mixed_game_library_continuity_handoff.v1",
    "skeleton.app.offline_mixed_library_epoch_handoff.v1",
})
MAX_PROTECTED_ROOTS = 64


class OfflineUncertainReceiptInspectionError(ValueError):
    """A possibly published receipt is not safely pinned or inspectable."""


def inspect_uncertain_receipt(
    receipt_file: str | Path,
    *,
    expected_receipt_sha256: str,
    protected_roots: Sequence[str | Path],
    authorized: bool,
) -> dict[str, object]:
    """Inspect only the receipt inode; do not infer that game replay passed.

    Caller must provide an independently obtained pin and original game
    custody paths. No digest is derived from an untrusted file and accepted
    as its own authority. A successful result is quarantine evidence only.
    """
    if authorized is not True:
        raise PermissionError("trusted local operator acknowledgement required")
    if (type(expected_receipt_sha256) is not str
            or _PIN.fullmatch(expected_receipt_sha256) is None):
        raise OfflineUncertainReceiptInspectionError(
            "independent lowercase SHA-256 receipt pin required"
        )
    if (type(protected_roots) not in (tuple, list)
            or not 1 <= len(protected_roots) <= MAX_PROTECTED_ROOTS
            or any(not (type(item) is str or isinstance(item, Path))
                   or not str(item) for item in protected_roots)):
        raise OfflineUncertainReceiptInspectionError(
            "bounded explicit original custody roots required"
        )
    target = _reject_protected_receipt(
        receipt_file, tuple(str(root) for root in protected_roots),
    )
    identity = _save_identity(target)
    stored = _read_envelope(target, expected_sha256=expected_receipt_sha256)
    if (
        type(stored) is not dict
        or stored.get("schema") not in _ALLOWED
        or stored.get("offline_gameplay_reexecuted") is not True
        or stored.get("release_certified") is not False
        or stored.get("package_signed") is not False
        or stored.get("native_device_qualified") is not False
        or stored.get("rights_certified") is not False
    ):
        raise OfflineUncertainReceiptInspectionError(
            "unrecognized or untrusted offline handoff envelope"
        )
    canonical = _canonical_bytes(stored)
    if (not 0 < len(canonical) <= MAX_RECEIPT_BYTES
            or not hmac.compare_digest(
                sha256(canonical).hexdigest(), expected_receipt_sha256,
            )
            or stored != _read_envelope(
                target, expected_sha256=expected_receipt_sha256,
            )
            or identity != _save_identity(target)):
        raise OfflineUncertainReceiptInspectionError(
            "receipt inode or independently pinned bytes changed"
        )
    return {
        "schema": SCHEMA,
        "status": "quarantined_receipt_bytes_pinned_replay_unverified",
        "receipt_sha256": expected_receipt_sha256,
        "receipt_schema": stored["schema"],
        "receipt_bytes": len(canonical),
        "receipt_integrity_verified": True,
        "independent_digest_required": True,
        "game_replay_reverified": False,
        "source_and_save_custody_reverified": False,
        "publication_durability_proven": False,
        "operator_quarantine_required": True,
        "read_only": True,
        "receipt_modified": False,
        "native_device_qualified": False,
        "package_signed": False,
        "rights_certified": False,
        "release_certified": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton app inspect-uncertain-offline-receipt",
        description="Quarantine triage of an independently pinned receipt, not game replay",
    )
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--expected-receipt-sha256", required=True)
    parser.add_argument("--protected-root", action="append", required=True)
    parser.add_argument("--trusted-local-operator", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = inspect_uncertain_receipt(
            args.receipt,
            expected_receipt_sha256=args.expected_receipt_sha256,
            protected_roots=args.protected_root,
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


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "SCHEMA", "OfflineUncertainReceiptInspectionError",
    "inspect_uncertain_receipt", "main",
]
