"""Independent post-publication verifier for Jeeves' original Godot ZIP.

Checks actual disk bytes, SHA identity, every native source file against the
bundled signed-content receipt, Zip metadata/path safety, and project/source
ownership. No runtime test is inferred from checksums alone.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
from typing import Any
import zipfile

from .studio_interaction_contract import digest

MAX_ARCHIVE_BYTES = 16 * 1024 * 1024
MAX_ENTRIES = 129
MAX_FILE_BYTES = 8 * 1024 * 1024
PROOF_NAME = "jeeves_source_receipt.json"


class NativeSourceVerificationError(ValueError):
    """Published original Godot source ZIP failed independent verification."""


def verify_published_godot_zip(
    path: Path, *, project_id: str, source_head_sha256: str | None,
    expected_archive_sha256: str,
) -> dict[str, Any]:
    if (not isinstance(path, Path) or not path.is_absolute()
            or path.is_symlink() or not path.is_file()):
        raise NativeSourceVerificationError("Godot candidate must be a real local file")
    if not isinstance(expected_archive_sha256, str) or len(expected_archive_sha256) != 64:
        raise NativeSourceVerificationError("expected published bytes SHA-256 is required")
    size = path.stat().st_size
    if size < 128 or size > MAX_ARCHIVE_BYTES:
        raise NativeSourceVerificationError("published archive exceeds bounded size")
    raw = path.read_bytes()
    if len(raw) != size or sha256(raw).hexdigest() != expected_archive_sha256:
        raise NativeSourceVerificationError("published artifact bytes differ from expected")
    try:
        with zipfile.ZipFile(path, "r") as archive:
            files = archive.infolist()
            names = [item.filename for item in files]
            if (len(files) < 4 or len(files) > MAX_ENTRIES
                    or len(names) != len(set(names))
                    or names.count(PROOF_NAME) != 1
                    or "project.godot" not in names
                    or "game/frontier/expedition.gd" not in names
                    or "game/frontier/expedition.tscn" not in names):
                raise NativeSourceVerificationError(
                    "Godot native game source archive is missing required files"
                )
            total = 0
            for item in files:
                name = item.filename
                pure = PurePosixPath(name)
                if (not name or pure.is_absolute() or ".." in pure.parts
                        or "\\" in name or name != pure.as_posix()
                        or name.endswith("/") or item.is_dir()
                        or item.file_size > MAX_FILE_BYTES
                        or item.compress_type != zipfile.ZIP_DEFLATED
                        or (item.external_attr >> 16) & 0o170000 != 0o100000):
                    raise NativeSourceVerificationError(
                        "Godot archive contains an unsafe or unsupported member"
                    )
                total += item.file_size
                if total > MAX_ARCHIVE_BYTES:
                    raise NativeSourceVerificationError("expanded Godot source exceeds bound")
            proof_raw = archive.read(PROOF_NAME)
            if len(proof_raw) > 96 * 1024:
                raise NativeSourceVerificationError("Godot source receipt is oversized")
            try:
                proof = json.loads(proof_raw)
            except (ValueError, UnicodeDecodeError) as exc:
                raise NativeSourceVerificationError(
                    "Godot source receipt cannot be parsed"
                ) from exc
            if (not isinstance(proof, dict)
                    or proof.get("schema_version") !=
                    "skeleton.jeeves.frontier_godot_source.v1"
                    or proof.get("project_id") != project_id
                    or proof.get("source_head_sha256") != source_head_sha256
                    or proof.get("godot_engine_launched") is not False
                    or proof.get("native_godot_playthrough_verified") is not False
                    or proof.get("real_python_route_playtest_passed") is not True):
                raise NativeSourceVerificationError(
                    "Godot source ownership or execution claims are invalid"
                )
            receipt_digest = proof.get("receipt_sha256")
            without = dict(proof)
            without.pop("receipt_sha256", None)
            if digest(without) != receipt_digest:
                raise NativeSourceVerificationError("embedded game-build evidence was changed")
            expected = proof.get("godot_file_hashes")
            if (not isinstance(expected, dict)
                    or set(expected) != set(names) - {PROOF_NAME}):
                raise NativeSourceVerificationError(
                    "native file evidence does not cover exact archive members"
                )
            for name in sorted(expected):
                source_bytes = archive.read(name)
                if sha256(source_bytes).hexdigest() != expected[name]:
                    raise NativeSourceVerificationError(
                        "published native game source does not match build proof"
                    )
    except (zipfile.BadZipFile, RuntimeError, OSError, UnicodeError) as exc:
        raise NativeSourceVerificationError("published Godot archive is unreadable") from exc
    return {
        "schema_version": "skeleton.jeeves.native_source_disk_verification.v1",
        "project_id": project_id,
        "source_head_sha256": source_head_sha256,
        "archive_sha256": expected_archive_sha256,
        "archive_bytes": size,
        "verified_file_count": len(expected),
        "embedded_evidence_sha256": receipt_digest,
        "all_emitted_file_hashes_verified": True,
        "actual_godot_execution_verified": False,
    }


__all__ = ["NativeSourceVerificationError", "verify_published_godot_zip"]
