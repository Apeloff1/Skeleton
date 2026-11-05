"""Portable, owner-private transport of sealed local Jeeves source capsules.

This module moves reviewed source BYTES between operator-owned machines. It
never imports generated modules, runs Git, installs a model, calls a provider
or touches the original checkout. Every archive is a bounded canonical JSON
envelope with exact base64 bytes and independently approved complete SHA-256
identities. A portable archive is not a signed package or a release.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import stat

from .desktop_capsule_source_closure import (
    ClosureSource, analyze_capsule_source_closure,
)
from .desktop_patch_export import _identical_parent, _pinned_private_directory
from .desktop_private_capsule import (
    MAX_CAPSULE_FILES, MAX_TOTAL_CAPSULE_BYTES, SEAL_NAME, SEAL_SCHEMA,
    _DIR, _NAME, _copy, _read_capsule_file, _capsule_tree, _new_destination,
    _strict_pairs, _nonfinite, verify_private_capsule,
)
from .desktop_workspace import _canonical, _relative, WorkspaceDeliveryHold
from .desktop_workspace_index import _allowed_name

SCHEMA = "jeeves.workspace.private-capsule-offline-transport.v1"
MAX_ARCHIVE_BYTES = 2500000
MAX_SEAL_BYTES = 16384
MAX_ARCHIVE_FILES = MAX_CAPSULE_FILES + 1
MAX_TOTAL_CONTENT = MAX_TOTAL_CAPSULE_BYTES + MAX_SEAL_BYTES
_FIELDS = frozenset({
    "schema", "status", "capsule_sha256", "seal_sha256", "file_count",
    "files", "source_code_executed", "release_certified",
})
_ROW_FIELDS = frozenset({"path", "sha256", "bytes", "content_b64"})
_SEAL_FIELDS = frozenset({
    "schema", "status", "capsule_sha256", "source_manifest_sha256",
    "patch_sha256", "python_graph_sha256", "python_closure_sha256",
    "unverified_source_import_count", "file_count", "files",
    "source_code_executed", "original_checkout_modified",
    "full_project_or_device_qualified", "release_certified",
})


class CapsuleTransportHold(ValueError):
    """Incomplete, unapproved, nonprivate or altered capsule transport."""


def _hash(value: bytes) -> str:
    return sha256(value).hexdigest()


def _sha(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(
        c in "0123456789abcdef" for c in value
    )


def _json(raw: bytes, ceiling: int) -> dict:
    if type(raw) is not bytes or not 1 <= len(raw) <= ceiling:
        raise CapsuleTransportHold("transport exceeds bounded private byte allowance")
    try:
        document = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_strict_pairs, parse_constant=_nonfinite,
        )
    except (ValueError, UnicodeError, TypeError, RecursionError, MemoryError) as exc:
        raise CapsuleTransportHold("malformed or ambiguous private transport") from exc
    if type(document) is not dict or _canonical(document) != raw:
        raise CapsuleTransportHold("private transport is not canonical JSON")
    return document


def _name(path: object, *, seal: bool = False) -> str:
    if type(path) is not str:
        raise CapsuleTransportHold("untrusted archive entry name")
    if seal and path == SEAL_NAME:
        return path
    if path == SEAL_NAME:
        raise CapsuleTransportHold("seal is a reserved metadata entry")
    try:
        parts = _relative(path)
    except (WorkspaceDeliveryHold, ValueError) as exc:
        raise CapsuleTransportHold("archive path traversal or absolute path denied") from exc
    if not all(
        _allowed_name(part, directory=i < len(parts) - 1)
        for i, part in enumerate(parts)
    ):
        raise CapsuleTransportHold("sensitive or unsupported source in capsule")
    return path


def _sealed_inventory(seal: dict) -> dict[str, dict]:
    if (
        set(seal) != _SEAL_FIELDS
        or seal["schema"] != SEAL_SCHEMA
        or seal["status"] != "private-source-capsule-complete-unexecuted"
        or any(not _sha(seal[key]) for key in (
            "capsule_sha256", "source_manifest_sha256", "patch_sha256",
            "python_graph_sha256", "python_closure_sha256",
        ))
        or any(seal[key] is not False for key in (
            "source_code_executed", "original_checkout_modified",
            "full_project_or_device_qualified", "release_certified",
        ))
        or type(seal["file_count"]) is not int
        or not 2 <= seal["file_count"] <= MAX_CAPSULE_FILES
        or type(seal["files"]) is not list
        or len(seal["files"]) != seal["file_count"]
        or type(seal["unverified_source_import_count"]) is not int
        or not 0 <= seal["unverified_source_import_count"] <= 2048
    ):
        raise CapsuleTransportHold("incomplete or altered private capsule seal")
    inventory: dict[str, dict] = {}
    total = 0
    originals = 0
    changes = 0
    for item in seal["files"]:
        if type(item) is not dict or set(item) != {
            "path", "kind", "sha256", "bytes",
        }:
            raise CapsuleTransportHold("invalid selected source metadata")
        name = _name(item["path"])
        if (
            name.casefold() in inventory
            or type(item["kind"]) is not str
            or item["kind"] not in ("selected-original", "new", "edit")
            or not _sha(item["sha256"])
            or type(item["bytes"]) is not int
            or not 1 <= item["bytes"] <= 65536
        ):
            raise CapsuleTransportHold("ambiguous or oversized source inventory")
        total += item["bytes"]
        originals += item["kind"] == "selected-original"
        changes += item["kind"] != "selected-original"
        if total > MAX_TOTAL_CAPSULE_BYTES or originals > 48 or changes > 24:
            raise CapsuleTransportHold("capsule exceeds reviewed source count or bytes")
        inventory[name.casefold()] = item
    names = [row["path"] for row in seal["files"]]
    if names != sorted(names, key=lambda x: (x.casefold(), x)):
        raise CapsuleTransportHold("noncanonical selected source order")
    if not originals or not changes:
        raise CapsuleTransportHold("capsule lacks selected originals or reviewed changes")
    return inventory


@dataclass(frozen=True, slots=True)
class TransportSnapshot:
    archive_sha256: str
    capsule_sha256: str
    seal_sha256: str
    files: tuple[tuple[str, bytes, str], ...]
    source_bytes: int
    original_count: int
    changed_count: int
    unknown_imports: int
    closure_sha256: str

    def public(self, status: str) -> dict[str, object]:
        return {
            "schema": SCHEMA,
            "status": status,
            "archive_sha256": self.archive_sha256,
            "capsule_sha256": self.capsule_sha256,
            "seal_sha256": self.seal_sha256,
            "python_closure_sha256": self.closure_sha256,
            "source_file_count": len(self.files) - 1,
            "selected_original_file_count": self.original_count,
            "reviewed_change_file_count": self.changed_count,
            "total_source_bytes": self.source_bytes,
            "unverified_external_or_unselected_imports": self.unknown_imports,
            "source_bytes_exported_to_stdout": False,
            "source_code_executed": False,
            "original_project_modified": False,
            "model_inference_executed": False,
            "release_certified": False,
        }


def _decode_archive(
    raw: bytes, *, expected_archive_sha256: str,
    expected_capsule_sha256: str, expected_seal_sha256: str,
) -> TransportSnapshot:
    if any(not _sha(x) for x in (
        expected_archive_sha256, expected_capsule_sha256,
        expected_seal_sha256,
    )) or _hash(raw) != expected_archive_sha256:
        raise CapsuleTransportHold("complete transport SHA-256 approval missing or stale")
    document = _json(raw, MAX_ARCHIVE_BYTES)
    if (
        frozenset(document) != _FIELDS
        or document["schema"] != SCHEMA
        or document["status"] != "sealed-private-source-bytes-unexecuted"
        or document["capsule_sha256"] != expected_capsule_sha256
        or document["seal_sha256"] != expected_seal_sha256
        or document["source_code_executed"] is not False
        or document["release_certified"] is not False
        or type(document["file_count"]) is not int
        or type(document["files"]) is not list
        or not 3 <= document["file_count"] <= MAX_ARCHIVE_FILES
        or len(document["files"]) != document["file_count"]
    ):
        raise CapsuleTransportHold("unapproved private source transport schema")
    files: list[tuple[str, bytes, str]] = []
    names: set[str] = set()
    total = 0
    for item in document["files"]:
        if type(item) is not dict or frozenset(item) != _ROW_FIELDS:
            raise CapsuleTransportHold("unexpected transport payload metadata")
        name = _name(item["path"], seal=True)
        if (
            name.casefold() in names or not _sha(item["sha256"])
            or type(item["bytes"]) is not int
            or not 1 <= item["bytes"] <= (
                MAX_SEAL_BYTES if name == SEAL_NAME else 65536
            )
            or type(item["content_b64"]) is not str
        ):
            raise CapsuleTransportHold("ambiguous, oversized or duplicate transport file")
        try:
            data = base64.b64decode(
                item["content_b64"].encode("ascii", "strict"), validate=True,
            )
        except (UnicodeError, ValueError, base64.binascii.Error) as exc:
            raise CapsuleTransportHold("invalid private source frame") from exc
        if (
            base64.b64encode(data).decode("ascii") != item["content_b64"]
            or len(data) != item["bytes"] or _hash(data) != item["sha256"]
        ):
            raise CapsuleTransportHold("transport frame bytes or SHA altered")
        total += len(data)
        if total > MAX_TOTAL_CONTENT:
            raise CapsuleTransportHold("source transport aggregate ceiling exceeded")
        files.append((name, data, item["sha256"]))
        names.add(name.casefold())
    if SEAL_NAME.casefold() not in names:
        raise CapsuleTransportHold("last-written completion seal is missing")
    ordered = [name for name, _, _ in files]
    if ordered != sorted(
        ordered, key=lambda name: (name != SEAL_NAME, name.casefold(), name),
    ):
        raise CapsuleTransportHold("transport source order is not deterministic")
    by_name = {name: data for name, data, _ in files}
    seal_raw = by_name[SEAL_NAME]
    if _hash(seal_raw) != expected_seal_sha256:
        raise CapsuleTransportHold("cold seal differs from independently approved SHA")
    seal = _json(seal_raw, MAX_SEAL_BYTES)
    inventory = _sealed_inventory(seal)
    if (
        seal["capsule_sha256"] != expected_capsule_sha256
        or seal["file_count"] + 1 != len(files)
        or set(inventory) != (names - {SEAL_NAME.casefold()})
    ):
        raise CapsuleTransportHold("private sealed source inventory differs from transport")
    source_records = []
    source_bytes = 0
    for name, data, digest in files:
        if name == SEAL_NAME:
            continue
        row = inventory[name.casefold()]
        if row["path"] != name or row["sha256"] != digest or row["bytes"] != len(data):
            raise CapsuleTransportHold("reviewed source does not match sealed metadata")
        source_records.append(ClosureSource(name, row["kind"], data, digest))
        source_bytes += len(data)
    graph = analyze_capsule_source_closure(
        tuple(source_records),
        source_manifest_sha256=seal["source_manifest_sha256"],
        source_patch_sha256=seal["patch_sha256"],
    )
    if (
        graph.graph_sha256 != seal["python_closure_sha256"]
        or graph.unverified_count != seal["unverified_source_import_count"]
    ):
        raise CapsuleTransportHold("selected source import closure changed in transit")
    return TransportSnapshot(
        archive_sha256=expected_archive_sha256,
        capsule_sha256=expected_capsule_sha256,
        seal_sha256=expected_seal_sha256,
        files=tuple(files), source_bytes=source_bytes,
        original_count=sum(row["kind"] == "selected-original"
                           for row in inventory.values()),
        changed_count=sum(row["kind"] != "selected-original"
                          for row in inventory.values()),
        unknown_imports=graph.unverified_count,
        closure_sha256=graph.graph_sha256,
    )


def _archive_path(path: str | Path, original_project_root: str) -> Path:
    candidate = _new_destination(path, original_project_root)
    if not _NAME.fullmatch(candidate.name):
        raise CapsuleTransportHold("archive name must be a safe private leaf")
    return candidate


def _load_private_archive(
    archive: str | Path, *, original_project_root: str,
    expected_archive_sha256: str, expected_capsule_sha256: str,
    expected_seal_sha256: str,
) -> TransportSnapshot:
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise CapsuleTransportHold("POSIX/WSL2 descriptor custody required")
    path = _archive_path(archive, original_project_root)
    parent = _pinned_private_directory(path)
    try:
        _identical_parent(path, parent)
        raw = _read_capsule_file(parent, path.name, MAX_ARCHIVE_BYTES)
        snapshot = _decode_archive(
            raw, expected_archive_sha256=expected_archive_sha256,
            expected_capsule_sha256=expected_capsule_sha256,
            expected_seal_sha256=expected_seal_sha256,
        )
        _identical_parent(path, parent)
        if _read_capsule_file(parent, path.name, MAX_ARCHIVE_BYTES) != raw:
            raise CapsuleTransportHold("archive replaced during cold inspection")
        return snapshot
    finally:
        os.close(parent)


def inspect_private_transport(
    archive: str | Path, *, original_project_root: str,
    expected_archive_sha256: str, expected_capsule_sha256: str,
    expected_seal_sha256: str,
) -> dict[str, object]:
    """Read-only independently SHA-approved transport inspection."""
    return _load_private_archive(
        archive, original_project_root=original_project_root,
        expected_archive_sha256=expected_archive_sha256,
        expected_capsule_sha256=expected_capsule_sha256,
        expected_seal_sha256=expected_seal_sha256,
    ).public("cold-private-source-archive-verified")


def export_private_transport(
    capsule_directory: str | Path, archive: str | Path, *,
    original_project_root: str,
    expected_capsule_sha256: str, expected_seal_sha256: str,
    approve_export: bool,
) -> dict[str, object]:
    """Read an approved completed capsule; create one private archive O_EXCL."""
    if approve_export is not True or any(not _sha(x) for x in (
        expected_capsule_sha256, expected_seal_sha256,
    )):
        raise CapsuleTransportHold("explicit original capsule transport consent required")
    capsule = _new_destination(capsule_directory, original_project_root)
    path = _archive_path(archive, original_project_root)
    if path.is_relative_to(capsule) or capsule.is_relative_to(path):
        raise CapsuleTransportHold("archive must be outside the source capsule")
    verify_private_capsule(
        capsule, original_project_root=original_project_root,
        expected_capsule_sha256=expected_capsule_sha256,
        expected_seal_sha256=expected_seal_sha256,
    )
    parent = _pinned_private_directory(capsule)
    directory_fd = None
    try:
        _identical_parent(capsule, parent)
        directory_fd = os.open(capsule.name, _DIR, dir_fd=parent)
        info = os.fstat(directory_fd)
        if (
            not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or info.st_mode & 0o077
        ):
            raise CapsuleTransportHold("source capsule is not owner-private")
        seal_raw = _read_capsule_file(directory_fd, SEAL_NAME, MAX_SEAL_BYTES)
        if _hash(seal_raw) != expected_seal_sha256:
            raise CapsuleTransportHold("approved private capsule seal changed")
        seal = _json(seal_raw, MAX_SEAL_BYTES)
        inventory = _sealed_inventory(seal)
        paths = [row["path"] for row in seal["files"]]
        files = [(SEAL_NAME, seal_raw)] + [
            (name, _read_capsule_file(directory_fd, name, inventory[name.casefold()]["bytes"]))
            for name in paths
        ]
        # Reject extra entries and unexpected directories before sealing a
        # transport. A completion seal alone cannot authorize extra files.
        actual, directories = _capsule_tree(directory_fd)
        expected_dirs = {
            "/".join(name.split("/")[:depth])
            for name in paths
            for depth in range(1, len(name.split("/")))
        }
        if actual != set(paths) | {SEAL_NAME} or directories != expected_dirs:
            raise CapsuleTransportHold("unexpected source capsule tree entries")
        _identical_parent(capsule, parent)
    finally:
        if directory_fd is not None:
            os.close(directory_fd)
        os.close(parent)
    document = {
        "schema": SCHEMA,
        "status": "sealed-private-source-bytes-unexecuted",
        "capsule_sha256": expected_capsule_sha256,
        "seal_sha256": expected_seal_sha256,
        "file_count": len(files),
        "files": [
            {"path": name, "sha256": _hash(data), "bytes": len(data),
             "content_b64": base64.b64encode(data).decode("ascii")}
            for name, data in files
        ],
        "source_code_executed": False,
        "release_certified": False,
    }
    raw = _canonical(document)
    if len(raw) > MAX_ARCHIVE_BYTES:
        raise CapsuleTransportHold("portable source archive exceeds finite bound")
    digest = _hash(raw)
    snapshot = _decode_archive(
        raw, expected_archive_sha256=digest,
        expected_capsule_sha256=expected_capsule_sha256,
        expected_seal_sha256=expected_seal_sha256,
    )
    # Reopen the complete source tree before publication. A replaced original
    # cannot silently become a valid transport from a stale inspection.
    verify_private_capsule(
        capsule, original_project_root=original_project_root,
        expected_capsule_sha256=expected_capsule_sha256,
        expected_seal_sha256=expected_seal_sha256,
    )
    target_parent = _pinned_private_directory(path)
    try:
        _identical_parent(path, target_parent)
        _copy(target_parent, path.name, raw, digest)
        os.fsync(target_parent)
        _identical_parent(path, target_parent)
        if _read_capsule_file(target_parent, path.name, MAX_ARCHIVE_BYTES) != raw:
            raise CapsuleTransportHold("private transport failed read-back verification")
    finally:
        os.close(target_parent)
    return {
        **snapshot.public("new-private-source-transport-exported"),
        "archive_bytes": len(raw),
        "private_archive_file_mode": "0600",
        "archive_source_cold_verified": True,
    }


def import_private_transport(
    archive: str | Path, destination: str | Path, *,
    original_project_root: str,
    expected_archive_sha256: str, expected_capsule_sha256: str,
    expected_seal_sha256: str, approve_import: bool,
) -> dict[str, object]:
    """Copy approved transport to NEW sealed owner-private source directory."""
    if approve_import is not True:
        raise CapsuleTransportHold("explicit offline capsule import consent required")
    snapshot = _load_private_archive(
        archive, original_project_root=original_project_root,
        expected_archive_sha256=expected_archive_sha256,
        expected_capsule_sha256=expected_capsule_sha256,
        expected_seal_sha256=expected_seal_sha256,
    )
    path = _new_destination(destination, original_project_root)
    archive_path = _archive_path(archive, original_project_root)
    if (
        path == archive_path or path.is_relative_to(archive_path)
        or archive_path.is_relative_to(path)
    ):
        raise CapsuleTransportHold("source destination must not contain archive")
    parent = _pinned_private_directory(path)
    folder = None
    try:
        _identical_parent(path, parent)
        os.mkdir(path.name, 0o700, dir_fd=parent)
        os.fsync(parent)
        folder = os.open(path.name, _DIR, dir_fd=parent)
        created = os.fstat(folder)
        linked = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        if (
            not stat.S_ISDIR(created.st_mode)
            or created.st_uid != os.getuid()
            or created.st_mode & 0o077
            or (created.st_dev, created.st_ino) != (linked.st_dev, linked.st_ino)
        ):
            raise CapsuleTransportHold("private imported capsule directory substituted")
        # Seal MUST be the final publication. A torn transfer is never a
        # complete package and is never auto-restored/reused.
        for name, data, digest in snapshot.files:
            if name != SEAL_NAME:
                _copy(folder, name, data, digest)
        for name, data, digest in snapshot.files:
            if name == SEAL_NAME:
                _copy(folder, name, data, digest)
        os.fsync(folder)
        os.fsync(parent)
        _identical_parent(path, parent)
        linked = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        if (created.st_dev, created.st_ino) != (linked.st_dev, linked.st_ino):
            raise CapsuleTransportHold("imported private source replaced before verification")
    finally:
        if folder is not None:
            os.close(folder)
        os.close(parent)
    proof = verify_private_capsule(
        path, original_project_root=original_project_root,
        expected_capsule_sha256=expected_capsule_sha256,
        expected_seal_sha256=expected_seal_sha256,
    )
    if (
        proof["python_closure_sha256"] != snapshot.closure_sha256
        or proof["file_count"] != len(snapshot.files) - 1
    ):
        raise CapsuleTransportHold("imported source closure or full file set differs")
    return {
        **snapshot.public("imported-private-source-capsule-cold-verified"),
        "source_bytes_cold_verified": True,
        "private_directory_mode": "0700",
        "private_file_mode": "0600",
        "incomplete_import_auto_deleted": False,
    }


__all__ = [
    "SCHEMA", "CapsuleTransportHold", "TransportSnapshot",
    "inspect_private_transport", "export_private_transport",
    "import_private_transport",
]
