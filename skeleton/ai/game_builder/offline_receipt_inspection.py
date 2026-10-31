"""Inspect an independently pinned offline game verification receipt without execution.

Receipt integrity is not a replacement for source replay, publisher signature,
original-content clearance, device qualification or release approval.
"""
from __future__ import annotations

from hashlib import sha256
import hmac
import os
from pathlib import Path
import re
from typing import Mapping

from .contracts import canonical_digest
from .dual_runtime_verify import (
    DualRuntimeVerificationError, _assert_original_root, _canonical_bytes,
    _json, _read, _root_fd,
)
from .offline_receipt_publication import _MAX_RECEIPT_BYTES, _NAME

SCHEMA = "skeleton.game_builder.offline_receipt_integrity.v1"
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_SUPPORTED = frozenset({
    "skeleton.game_builder.dual_runtime_verification.v1",
    "skeleton.game_builder.offline_export_batch_receipt.v1",
    "skeleton.game_builder.offline_export_batch_delta.v1",
})


class ReceiptInspectionError(ValueError):
    """The archived receipt is untrusted, changed or unsupported."""


def inspect_verified_receipt(
    receipt_path: str | Path, *, expected_sha256: str, authorized: bool,
    expected_source: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Read a bounded nofollow JSON receipt against a separately held digest."""
    if authorized is not True:
        raise PermissionError("operator authorization required for receipt inspection")
    if type(expected_sha256) is not str or not _HEX.fullmatch(expected_sha256):
        raise ReceiptInspectionError("independent receipt SHA-256 pin required")
    path = Path(receipt_path).expanduser().absolute()
    if not _NAME.fullmatch(path.name):
        raise ReceiptInspectionError("unsafe receipt filename")
    try:
        parent_fd = _root_fd(path.parent)
    except (DualRuntimeVerificationError, OSError, TypeError, ValueError) as exc:
        raise ReceiptInspectionError("unsafe receipt parent") from exc
    try:
        raw = _read(parent_fd, path.name, _MAX_RECEIPT_BYTES)
        if not hmac.compare_digest(sha256(raw).hexdigest(), expected_sha256):
            raise ReceiptInspectionError("receipt differs from independent pin")
        payload = _json(raw, _MAX_RECEIPT_BYTES)
        if raw != _canonical_bytes(payload):
            raise ReceiptInspectionError("noncanonical receipt bytes")
        kind = payload.get("schema")
        if kind not in _SUPPORTED:
            raise ReceiptInspectionError("unsupported receipt schema")
        if (payload.get("release_certified") is not False
                or payload.get("rights_certified", False) is not False):
            raise ReceiptInspectionError("receipt claims unqualified release or rights")
        if kind == "skeleton.game_builder.offline_export_batch_delta.v1":
            if payload.get("both_cohorts_replayed") is not True:
                raise ReceiptInspectionError("delta replay evidence missing")
        elif payload.get("offline_gameplay_reexecuted") is not True:
            raise ReceiptInspectionError("game replay evidence missing")
        recorded_digest = payload.get("receipt_digest")
        if recorded_digest is not None:
            body = {key: value for key, value in payload.items()
                    if key != "receipt_digest"}
            if (type(recorded_digest) is not str
                    or not hmac.compare_digest(
                        recorded_digest, canonical_digest(body),
                    )):
                raise ReceiptInspectionError("recorded receipt digest differs")
        # A historical receipt cannot be paired with an unrelated live game.
        # Compare the complete canonical source/replay identity, not only a
        # project name or a digest selected from the untrusted receipt itself.
        if expected_source is not None:
            if kind != "skeleton.game_builder.dual_runtime_verification.v1":
                raise ReceiptInspectionError("receipt is not a single-game replay")
            if type(expected_source) is not dict:
                raise ReceiptInspectionError("canonical live source proof required")
            identity_fields = (
                "schema", "project_id", "manifest_sha256", "world_digest",
                "replay_digest", "verified_files", "verified_bytes",
                "replayed_actions", "offline_gameplay_reexecuted",
                "godot_executed", "rights_certified", "release_certified",
            )
            for field in identity_fields:
                if field not in expected_source or field not in payload:
                    raise ReceiptInspectionError("incomplete source/receipt identity")
                expected = expected_source[field]
                actual = payload[field]
                if type(actual) is not type(expected):
                    raise ReceiptInspectionError("source/receipt identity type mismatch")
                if type(expected) is str:
                    matches = hmac.compare_digest(actual, expected)
                else:
                    matches = actual == expected
                if not matches:
                    raise ReceiptInspectionError("receipt belongs to different source")
        # A second pinned descriptor read rejects concurrent rewrites after
        # the first pass. This is an integrity check, not a replay of the game.
        if _read(parent_fd, path.name, _MAX_RECEIPT_BYTES) != raw:
            raise ReceiptInspectionError("receipt changed during inspection")
        _assert_original_root(path.parent, parent_fd)
        return {
            "schema": SCHEMA,
            "receipt_schema": kind,
            "receipt_sha256": expected_sha256,
            "recorded_receipt_digest": recorded_digest,
            "receipt_integrity_verified": True,
            "source_binding_verified": expected_source is not None,
            "gameplay_reexecuted_now": False,
            "native_hardware_tested": False,
            "release_certified": False,
        }
    except ReceiptInspectionError:
        raise
    except (DualRuntimeVerificationError, OSError, UnicodeError, TypeError, ValueError) as exc:
        raise ReceiptInspectionError("unsafe or invalid receipt") from exc
    finally:
        os.close(parent_fd)


__all__ = ["ReceiptInspectionError", "inspect_verified_receipt", "SCHEMA"]
