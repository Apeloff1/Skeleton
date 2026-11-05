"""Portable, bounded, source-bound original game play bundles.

A bundle embeds its independently verified homebrew capsule and replayable
session so a recipient can reopen it offline. The checksum is an integrity
receipt, not a signature or independent proof of content ownership.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from .game_play_session import (
    fork_play_session, resume_play_session, verify_play_session,
)

SCHEMA = "skeleton.game.play_bundle.v1"
MAX_BUNDLE_BYTES = 150 * 1024
_BUNDLE_KEYS = frozenset((
    "schema_version", "capsule", "session", "body_bytes", "bundle_sha256",
))


class GamePlayBundleError(ValueError):
    """Untrusted, corrupt, oversized or non-replayable portable play bundle."""


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise GamePlayBundleError("noncanonical portable play bundle") from exc


def _body(capsule: Any, session: Any) -> dict[str, Any]:
    # Verify the original project, rights, scene, platform claims and
    # replayed controller history before admitting any bundled content.
    verify_play_session(capsule, session)
    return {
        "schema_version": SCHEMA,
        "capsule": capsule,
        "session": session,
    }


def pack_play_bundle(capsule: Any, session: Any) -> dict[str, Any]:
    """Create a self-contained offline JSON play/save bundle."""
    body = _body(capsule, session)
    raw = _canonical(body)
    if len(raw) > MAX_BUNDLE_BYTES:
        raise GamePlayBundleError("portable play bundle exceeded 150-KiB budget")
    return {
        **body,
        "body_bytes": len(raw),
        "bundle_sha256": hashlib.sha256(raw).hexdigest(),
    }


def verify_play_bundle(bundle: Any) -> dict[str, Any]:
    """Reject modified data, forged counters, unsupported schemas or bad replay."""
    if type(bundle) is not dict or set(bundle) != _BUNDLE_KEYS:
        raise GamePlayBundleError("portable play bundle schema mismatch")
    if bundle["schema_version"] != SCHEMA:
        raise GamePlayBundleError("unsupported portable play bundle version")
    body = {
        "schema_version": bundle["schema_version"],
        "capsule": bundle["capsule"],
        "session": bundle["session"],
    }
    raw = _canonical(body)
    if (
        len(raw) > MAX_BUNDLE_BYTES
        or type(bundle["body_bytes"]) is not int
        or bundle["body_bytes"] != len(raw)
        or type(bundle["bundle_sha256"]) is not str
        or bundle["bundle_sha256"] != hashlib.sha256(raw).hexdigest()
    ):
        raise GamePlayBundleError("portable play bundle integrity mismatch")
    receipt = verify_play_session(bundle["capsule"], bundle["session"])
    return {
        "schema_version": "skeleton.game.play_bundle.verify.v1",
        "bundle_sha256": bundle["bundle_sha256"],
        "capsule_sha256": receipt["capsule_sha256"],
        "session_sha256": receipt["session_sha256"],
        "frame_count": receipt["frame_count"],
        "victory_frame": receipt["victory_frame"],
        "offline_replay_verified": True,
        "native_export_created": False,
        "release_rights_independently_verified": False,
    }


def resume_play_bundle(bundle: Any, controls: Any) -> dict[str, Any]:
    """Reopen a portable bundle, validate its source and append input frames."""
    verify_play_bundle(bundle)
    updated = resume_play_session(bundle["capsule"], bundle["session"], controls)
    return pack_play_bundle(bundle["capsule"], updated)


def fork_play_bundle(bundle: Any, frame: Any, controls: Any) -> dict[str, Any]:
    """Create an independent portable alternate timeline after full replay."""
    verify_play_bundle(bundle)
    session = fork_play_session(
        bundle["capsule"], bundle["session"], frame, controls,
    )
    return pack_play_bundle(bundle["capsule"], session)


__all__ = [
    "SCHEMA", "MAX_BUNDLE_BYTES", "GamePlayBundleError",
    "pack_play_bundle", "verify_play_bundle", "resume_play_bundle",
    "fork_play_bundle",
]
