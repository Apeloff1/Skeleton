"""Real offline HTML5 playable bundle gated by independent canonical quest proofs.

Only the registered original catalog is allowed to provide playable HTML.
No arbitrary authored HTML is accepted, and source/replay evidence is rebuilt
before every publication or restore. This is NOT native/device qualification.
"""
from __future__ import annotations

from hashlib import sha256
import io
import os
from pathlib import Path
import secrets
import stat
from typing import Any, Mapping
import zipfile

from .studio_ecosystem_catalog import compile_preview, read_blueprint
from .studio_ecosystem_quest import StudioQuestError, compile_quest_program
from .studio_ecosystem_scene_schedule import (
    _canonical, _digest, _open_directory, _write_all,
)
from .studio_quest_readiness import (
    compile_quest_readiness_handoff, replay_quest_readiness,
)

SCHEMA = "skeleton.game_builder.studio_quest_readiness_playable.v1"
FILENAME = "studio_quest_readiness_playable.zip"
MAX_BUNDLE_BYTES = 8 * 1024 * 1024
_MEMBERS = ("index.html", "quest_readiness.json",
            "quest_readiness_handoff.json", "manifest.json")


def compile_quest_readiness_playable(
    documents: Mapping[str, Any], readiness: object, *, authorized: bool,
) -> tuple[dict[str, Any], bytes]:
    """Compile a real catalog HTML5 game only after both proof owners pass."""
    if authorized is not True:
        raise PermissionError("readiness playable requires operator authorization")
    verified = replay_quest_readiness(documents, readiness, authorized=True)
    if verified["playable_handoff_allowed"] is not True:
        raise StudioQuestError("unproved quest readiness blocks playable bundle")
    project_id = verified["project_id"]
    # Do not let a caller mix a valid proof with a different project or an
    # arbitrary HTML blob. The registered catalog remains the sole game owner.
    catalog = read_blueprint(project_id)
    if (_canonical(catalog) != _canonical(documents)
            or compile_quest_program(catalog).source_digest !=
            verified["source_digest"]):
        raise StudioQuestError("playable catalog differs from proven quest source")
    proof_handoff = compile_quest_readiness_handoff(
        catalog, verified, authorized=True)
    compiled = compile_preview(project_id, authorized=True)
    html = compiled.playable.html.encode("utf-8", "strict")
    game_receipt = compiled.receipt()
    if (type(game_receipt) is not dict
            or game_receipt.get("project_id") != project_id
            or game_receipt.get("validated_gameplay_proof") is not True
            or game_receipt.get("html_sha256") != sha256(html).hexdigest()
            or not html.lstrip().lower().startswith((b"<!doctype html", b"<html"))):
        raise StudioQuestError("catalog HTML5 playable proof mismatch")
    files = {
        "index.html": html,
        "quest_readiness.json": _canonical(verified) + b"\n",
        "quest_readiness_handoff.json": _canonical(proof_handoff) + b"\n",
    }
    if sum(len(value) for value in files.values()) > MAX_BUNDLE_BYTES:
        raise StudioQuestError("readiness playable sources exceed byte budget")
    manifest: dict[str, Any] = {
        "schema": SCHEMA,
        "project_id": project_id,
        "quest_source_digest": verified["source_digest"],
        "initial_session_digest": verified["initial_session_digest"],
        "readiness_digest": verified["readiness_digest"],
        "readiness_handoff_digest": proof_handoff["handoff_digest"],
        "canonical_playable_receipt": game_receipt,
        "file_hashes": {
            name: sha256(data).hexdigest() for name, data in sorted(files.items())
        },
        "canonical_quest_replay_verified": True,
        "canonical_html5_gameplay_replay_verified": True,
        "native_gameplay_verified": False,
        "native_device_verified": False,
        "asset_rights_verified": False,
        "release_certified": False,
    }
    manifest["manifest_digest"] = _digest(manifest)
    files["manifest.json"] = _canonical(manifest) + b"\n"
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=9, allowZip64=False) as archive:
        for name in _MEMBERS:
            entry = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100600 << 16
            archive.writestr(entry, files[name])
    bundle = out.getvalue()
    if not 0 < len(bundle) <= MAX_BUNDLE_BYTES:
        raise StudioQuestError("readiness playable bundle exceeds byte budget")
    manifest["bundle_sha256"] = sha256(bundle).hexdigest()
    manifest["bundle_bytes"] = len(bundle)
    return manifest, bundle


def publish_quest_readiness_playable(
    documents: Mapping[str, Any], readiness: object, manifest: object,
    bundle: object, directory: Path, *, authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("playable publication requires authorization")
    if (type(manifest) is not dict or manifest.get("schema") != SCHEMA
            or type(bundle) is not bytes or not 0 < len(bundle) <= MAX_BUNDLE_BYTES
            or sha256(bundle).hexdigest() != manifest.get("bundle_sha256")):
        raise StudioQuestError("invalid readiness playable publication")
    rebuilt, original = compile_quest_readiness_playable(
        documents, readiness, authorized=True)
    if rebuilt != manifest or original != bundle:
        raise StudioQuestError("playable publication differs from source replay")
    fd = _open_directory(directory)
    temporary = ".quest-playable-" + secrets.token_hex(16) + ".tmp"
    created = False
    try:
        output = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                         os.O_NOFOLLOW, 0o600, dir_fd=fd)
        created = True
        try:
            _write_all(output, bundle)
            os.fsync(output)
        finally:
            os.close(output)
        os.link(temporary, FILENAME, src_dir_fd=fd, dst_dir_fd=fd,
                follow_symlinks=False)
        os.fsync(fd)
    finally:
        try:
            if created:
                os.unlink(temporary, dir_fd=fd)
        finally:
            os.close(fd)
    return {
        "file": FILENAME, "bundle_sha256": manifest["bundle_sha256"],
        "bytes": len(bundle), "file_write_performed": True,
        "release_certified": False,
    }


def verify_quest_readiness_playable(
    documents: Mapping[str, Any], readiness: object, directory: Path, *,
    authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("playable restore requires authorization")
    fd = _open_directory(directory)
    try:
        handle = os.open(FILENAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=fd)
        try:
            before = os.fstat(handle)
            if (not stat.S_ISREG(before.st_mode)
                    or not 0 < before.st_size <= MAX_BUNDLE_BYTES
                    or (os.name == "posix"
                        and (before.st_uid != os.getuid() or before.st_mode & 0o077
                             or before.st_nlink != 1))):
                raise StudioQuestError("readiness playable must be private regular file")
            chunks: list[bytes] = []
            remaining = MAX_BUNDLE_BYTES + 1
            while remaining:
                chunk = os.read(handle, min(65536, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            after = os.fstat(handle)
            if ((after.st_size, after.st_mtime_ns, after.st_ctime_ns, after.st_ino)
                    != (before.st_size, before.st_mtime_ns, before.st_ctime_ns,
                        before.st_ino)):
                raise StudioQuestError("readiness playable changed during read")
        finally:
            os.close(handle)
    finally:
        os.close(fd)
    raw = b"".join(chunks)
    if len(raw) != before.st_size:
        raise StudioQuestError("readiness playable truncated during read")
    manifest, expected = compile_quest_readiness_playable(
        documents, readiness, authorized=True)
    if raw != expected:
        raise StudioQuestError("readiness playable differs from canonical rebuild")
    return manifest
