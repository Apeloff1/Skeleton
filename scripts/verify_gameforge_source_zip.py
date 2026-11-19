"""Inspect or reopen a portable GameForge source ZIP without executing it.

Use: python -m scripts.verify_gameforge_source_zip game.zip --expected-sha256 FULL_DIGEST
Add --output NEW_DIRECTORY to write verified sources, never overwrite a project.
The expected digest must come from the original Forge run through a trusted
channel. Neither ZIP metadata nor the truncated filename authenticates it.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import io
import json
import os
import re
import stat
import struct
import sys
import zipfile
from pathlib import Path
from typing import Any

from skeleton.forge.source_manifest import source_manifest

MAX_ZIP_BYTES = 9 * 1024 * 1024
MAX_SOURCE_BYTES = 8 * 1024 * 1024
MAX_FILES = 256
_DIGEST = re.compile(r"[0-9a-f]{64}")
_SEGMENT = re.compile(r"[a-zA-Z0-9_.-]{1,120}")
_DEVICES = {"con", "nul", "aux", "prn"} | {
    f"{prefix}{digit}" for prefix in ("com", "lpt") for digit in range(1, 10)
}


class PortableSourceError(ValueError):
    """A ZIP or destination fails the portable-source contract."""


def _safe_path(name: str) -> bool:
    return (type(name) is str and 0 < len(name) <= 240
            and all(part and not part.startswith(".") and not part.endswith(".")
                    and _SEGMENT.fullmatch(part) is not None
                    and part.split(".")[0].lower() not in _DEVICES
                    for part in name.split("/")))


def _read_zip(path: Path) -> bytes:
    # The bounded in-memory snapshot prevents subsequent path replacement
    # from changing the bytes inspected by the ZIP reader.
    flags = (os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
             | getattr(os, "O_NONBLOCK", 0))
    if path.is_symlink():
        raise PortableSourceError("archive must be a regular file")
    # Inspect the raw descriptor before wrapping it as a Python file:
    # directory descriptors may be rejected by fdopen itself on some hosts.
    if not path.is_file():
        raise PortableSourceError("archive is not a file")
    fd = os.open(path, flags)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or not 22 <= info.st_size <= MAX_ZIP_BYTES:
            raise PortableSourceError("archive exceeds portable ZIP budget or is not a file")
        with os.fdopen(fd, "rb", closefd=False) as handle:
            raw = handle.read(MAX_ZIP_BYTES + 1)
    finally:
        os.close(fd)
    if len(raw) != info.st_size or len(raw) > MAX_ZIP_BYTES:
        raise PortableSourceError("archive changed size during bounded read")
    return raw


def _validate_zip_layout(raw: bytes, members: list[zipfile.ZipInfo]) -> None:
    """Validate the exact single-disk stored ZIP layout, not just its index.

    No self-extracting prefix, trailing payload, overlapping members, extra
    unindexed local entries, data descriptors or divergent local metadata.
    The Godot source digest is not an authorization for arbitrary ZIP bytes.
    """
    end = len(raw) - 22
    signature, disk, central_disk, count_disk, count, size, offset, comment = struct.unpack_from(
        "<4s4H2IH", raw, end,
    )
    if (signature != b"PK\x05\x06" or disk or central_disk or comment
            or count != count_disk or count != len(members)
            or offset + size != end or offset > end):
        raise PortableSourceError("invalid or noncanonical ZIP end record")
    cursor = 0
    central_cursor = offset
    for member in members:
        if member.header_offset != cursor or cursor + 30 > offset:
            raise PortableSourceError("unindexed or overlapping ZIP source data")
        local = struct.unpack_from("<4s5H3I2H", raw, cursor)
        signature, version, flags, method, _, _, crc, packed, unpacked, name_len, extra_len = local
        if (signature != b"PK\x03\x04" or version > 20 or flags != member.flag_bits
                or method != member.compress_type or crc != member.CRC
                or packed != member.compress_size or unpacked != member.file_size
                or extra_len or name_len != len(member.filename)):
            raise PortableSourceError("ZIP local header differs from source inventory")
        name_at = cursor + 30
        data_at = name_at + name_len
        if data_at + packed > offset or raw[name_at:data_at] != member.filename.encode("ascii"):
            raise PortableSourceError("ZIP local member name or bounds mismatch")
        cursor = data_at + packed
        if central_cursor + 46 > end:
            raise PortableSourceError("truncated ZIP central directory")
        fields = struct.unpack_from("<4s6H3I5H2I", raw, central_cursor)
        (signature, _, version, flags, method, _, _, crc, packed, unpacked,
         name_len, extra_len, comment_len, disk, _, _, local_offset) = fields
        if (signature != b"PK\x01\x02" or version > 20 or flags != member.flag_bits
                or method != member.compress_type or crc != member.CRC
                or packed != member.compress_size or unpacked != member.file_size
                or disk or extra_len or comment_len or local_offset != member.header_offset
                or name_len != len(member.filename)):
            raise PortableSourceError("ZIP central member metadata mismatch")
        name_at = central_cursor + 46
        central_cursor = name_at + name_len
        if central_cursor > end or raw[name_at:central_cursor] != member.filename.encode("ascii"):
            raise PortableSourceError("ZIP central name or bounds mismatch")
    if cursor != offset or central_cursor != end:
        raise PortableSourceError("unindexed ZIP content is not portable source")


def _strict_document(value: str, byte_limit: int) -> dict[str, Any]:
    """Decode bounded inert JSON; repeated names and nonfinite values are invalid."""
    if len(value) > byte_limit or len(value.encode("utf-8")) > byte_limit:
        raise ValueError("design document exceeds budget")

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("duplicate design document key")
            result[key] = item
        return result

    def no_constant(_: str) -> Any:
        raise ValueError("nonfinite design document value")

    document = json.loads(value, object_pairs_hook=unique, parse_constant=no_constant)
    if type(document) is not dict:
        raise ValueError("design document must be an object")
    return document


def inspect_project(files: dict[str, str]) -> dict[str, Any]:
    """Reconcile source-bound design artifacts against this installed compiler.

    A historical project may have a valid full digest yet no longer match the
    current templates. Report that distinction, never silently regenerate it.
    """
    from skeleton.context.galaxy_profile import (
        ARTIFACT_PATH, PLAYABLE_RECEIPT_PATH, attach_galaxy_profile,
        compile_galaxy_playable_axes, galaxy_profile_receipt,
        normalise_galaxy_profile, seal_galaxy_playable_controls,
    )
    from skeleton.forge.archetype_content import content_archetypes, verify_archetype_content
    from skeleton.forge.playable_portal import SCRIPT_PATH, verify_playable_portal
    from skeleton.forge.playable_tuning import SOURCE_PATH

    modes = [name for name in content_archetypes()
             if any(path in files for path in (
                 f"scenes/archetypes/{name}/main.tscn",
                 f"scripts/archetypes/{name}/player_controller.gd",
                 f"scripts/archetypes/{name}/core_loop.gd",
             ))]
    report: dict[str, Any] = {
        "schema": "skeleton.gameforge.portable_project_inspection.v1",
        "playable_modes": modes,
        "native_template": "absent",
        "tuning": "absent",
        "galaxy_profile": "absent",
        "galaxy_controls": "absent",
        "playable_portal": "absent",
        "native_execution_qualified": False,
    }
    errors: list[str] = []
    profile = None
    if ARTIFACT_PATH in files:
        try:
            profile = normalise_galaxy_profile(_strict_document(files[ARTIFACT_PATH], 600_001))
            if profile is None or attach_galaxy_profile({}, profile)[ARTIFACT_PATH] != files[ARTIFACT_PATH]:
                raise ValueError("noncanonical authoring profile")
            report["galaxy_profile"] = "verified"
            report["profile_sha256"] = galaxy_profile_receipt(profile)["sha256"]
        except (ValueError, TypeError, KeyError, RecursionError, OverflowError):
            profile = None
            report["galaxy_profile"] = "invalid"
            errors.append("galaxy_profile")
    tuning: dict[str, Any] = {}
    axes: dict[str, float] = {}
    if SOURCE_PATH in files:
        try:
            tuning = _strict_document(files[SOURCE_PATH], 32 * 1024)
            if (tuning.get("schema") != "skeleton.gameforge.playable_tuning.v1"
                    or type(tuning.get("axes")) is not dict or len(modes) != 1
                    or tuning.get("mode") != modes[0]):
                raise ValueError("tuning mode or schema mismatch")
            axes = dict(tuning["axes"])
            report["tuning"] = "unmatched"
        except (ValueError, TypeError, KeyError, RecursionError, OverflowError):
            report["tuning"] = "invalid"
            errors.append("tuning")
    galaxy_receipt = None
    effective_axes = axes
    if PLAYABLE_RECEIPT_PATH in files:
        try:
            galaxy_receipt = _strict_document(files[PLAYABLE_RECEIPT_PATH], 64 * 1024)
            effective_axes = galaxy_receipt["effective_axes"]
            if (profile is None or len(modes) != 1 or galaxy_receipt.get("mode") != modes[0]
                    or type(effective_axes) is not dict or type(galaxy_receipt.get("axes")) is not list
                    or len(galaxy_receipt["axes"]) > 10):
                raise ValueError("unbound Galaxy control receipt")
            report["galaxy_controls"] = "unmatched"
        except (ValueError, TypeError, KeyError, RecursionError, OverflowError):
            report["galaxy_controls"] = "invalid"
            errors.append("galaxy_controls")
            galaxy_receipt = None
            effective_axes = axes
    if len(modes) == 1:
        mode = modes[0]
        try:
            exact = verify_archetype_content(files, mode, operator_axes=effective_axes)
        except (ValueError, TypeError, KeyError, RuntimeError, OverflowError):
            exact = False
        report["native_template"] = "verified" if exact else "historical_or_modified"
        if not exact:
            errors.append("native_template")
        if exact and SOURCE_PATH in files and report["tuning"] != "invalid":
            report["tuning"] = "verified"
            report["mapped_axes"] = tuning["mapped_axes"]
            report["unmapped_axes"] = tuning["unmapped_axes"]
            report["applied"] = tuning["applied"]
        if galaxy_receipt is not None:
            try:
                inherited = {
                    row["axis"] for row in galaxy_receipt["axes"]
                    if row["authority"] == "galaxy_matrix"
                }
                overrides = {key: value for key, value in effective_axes.items() if key not in inherited}
                resolved, pending = compile_galaxy_playable_axes(profile, mode, overrides)
                baseline = {key: value for key, value in files.items() if key != PLAYABLE_RECEIPT_PATH}
                sealed, _ = seal_galaxy_playable_controls(baseline, pending)
                if resolved != effective_axes or sealed[PLAYABLE_RECEIPT_PATH] != files[PLAYABLE_RECEIPT_PATH]:
                    raise ValueError("Galaxy authoring receipt differs from source")
                report["galaxy_controls"] = "verified"
                report["mapped_matrix_dials"] = galaxy_receipt["mapped_matrix_dials"]
                report["unmapped_matrix_dials"] = galaxy_receipt["unmapped_matrix_dials"]
            except (ValueError, TypeError, KeyError, AttributeError, RuntimeError, RecursionError, OverflowError):
                errors.append("galaxy_controls")
        if SCRIPT_PATH in files:
            start_native = verify_playable_portal(files, mode, start_in_prototype=True)
            start_world = verify_playable_portal(files, mode, start_in_prototype=False)
            report["playable_portal"] = "verified" if start_native or start_world else "historical_or_modified"
            if start_native or start_world:
                report["startup"] = "prototype" if start_native else "world"
            else:
                errors.append("playable_portal")
    elif modes:
        report["native_template"] = "multiple_modes"
        errors.append("native_template")
    elif SOURCE_PATH in files or PLAYABLE_RECEIPT_PATH in files or SCRIPT_PATH in files:
        errors.append("orphaned_playable_artifact")
    report["current_template_compatible"] = not errors and report["native_template"] == "verified"
    report["findings"] = sorted(set(errors))
    return report


def inspect_archive(raw: bytes, expected_sha256: str) -> tuple[dict[str, str], dict[str, Any]]:
    """Return verified source strings and a detached inspection receipt.

    The ZIP is restricted to the stored-text format emitted by GameForge.
    A correct full source manifest digest proves source identity only.
    """
    if type(expected_sha256) is not str or _DIGEST.fullmatch(expected_sha256) is None:
        raise PortableSourceError("a full lowercase SHA-256 source manifest digest is required")
    if type(raw) is not bytes or not 22 <= len(raw) <= MAX_ZIP_BYTES:
        raise PortableSourceError("archive exceeds portable ZIP budget")
    files: dict[str, str] = {}
    leaves: set[str] = set()
    directories: dict[str, str] = {}
    total = 0
    try:
        with zipfile.ZipFile(io.BytesIO(raw), "r") as archive:
            members = archive.infolist()
            if archive.comment or not 0 < len(members) <= MAX_FILES:
                raise PortableSourceError("invalid ZIP member inventory")
            if any(not _safe_path(member.filename) for member in members):
                raise PortableSourceError("unsafe ZIP member name")
            _validate_zip_layout(raw, members)
            for member in members:
                name = member.filename
                kind = stat.S_IFMT(member.external_attr >> 16)
                if (not _safe_path(name) or member.orig_filename != name
                        or member.is_dir() or kind not in (0, stat.S_IFREG)
                        or member.flag_bits not in (0, 0x800)
                        or member.compress_type != zipfile.ZIP_STORED
                        or member.compress_size != member.file_size
                        or member.extra or member.comment
                        or not 0 <= member.file_size <= MAX_SOURCE_BYTES - total):
                    raise PortableSourceError("unsafe or over-budget ZIP member")
                folded = name.lower()
                if folded in leaves or folded in directories:
                    raise PortableSourceError("duplicate or file-directory ZIP member")
                parts = name.split("/")
                for depth in range(1, len(parts)):
                    prefix = "/".join(parts[:depth])
                    alias = prefix.lower()
                    if alias in leaves or (alias in directories and directories[alias] != prefix):
                        raise PortableSourceError("ambiguous ZIP directory")
                    directories[alias] = prefix
                leaves.add(folded)
                with archive.open(member, "r") as stream:
                    data = stream.read(member.file_size + 1)
                if len(data) != member.file_size:
                    raise PortableSourceError("ZIP member size mismatch")
                total += len(data)
                files[name] = data.decode("utf-8", errors="strict")
    except (zipfile.BadZipFile, UnicodeError, RuntimeError, NotImplementedError, EOFError, struct.error) as exc:
        raise PortableSourceError("invalid portable ZIP data") from exc
    try:
        manifest = source_manifest(files)
    except (ValueError, TypeError, UnicodeError) as exc:
        raise PortableSourceError("invalid Godot project source inventory") from exc
    digest = str(manifest["sha256"])
    if not hmac.compare_digest(digest, expected_sha256):
        raise PortableSourceError("source manifest SHA-256 mismatch")
    return files, {
        "schema": "skeleton.gameforge.portable_source_inspection.v1",
        "source_manifest": manifest,
        "archive_sha256": hashlib.sha256(raw).hexdigest(),
        "source_bytes": total,
        "archive_bytes": len(raw),
        "source_verified": True,
        "native_execution_qualified": False,
        "project_inspection": inspect_project(files),
    }


def reopen_archive(path: Path, expected_sha256: str, output: Path | None = None,
                   *, require_current_template: bool = False) -> dict[str, Any]:
    files, receipt = inspect_archive(_read_zip(path), expected_sha256)
    if require_current_template and not receipt["project_inspection"]["current_template_compatible"]:
        raise PortableSourceError("project does not match the current native template")
    if output is not None:
        # Deliberately require an absent named directory below an existing,
        # trusted local parent. Never merge with or overwrite existing sources.
        # A write failure may leave partial new files; do not recursively
        # delete a destination that might have been modified by another process.
        if output.name in ("", ".", "..") or not output.parent.is_dir():
            raise PortableSourceError("output must be a named new directory under an existing parent")
        if output.parent.is_symlink() or output.is_symlink():
            raise PortableSourceError("symlink destination is not allowed")
        try:
            output.mkdir(mode=0o700, exist_ok=False)
        except FileExistsError as exc:
            raise PortableSourceError("output already exists; choose a new directory") from exc
        for name, body in sorted(files.items()):
            target = output.joinpath(*name.split("/"))
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with target.open("xb") as handle:
                handle.write(body.encode("utf-8", errors="strict"))
        receipt["reopened"] = True
    else:
        receipt["reopened"] = False
    return receipt


def compare_archives(
    original: Path, original_sha256: str, revised: Path, revised_sha256: str,
) -> dict[str, Any]:
    """Compare two independently verified, bounded source snapshots.

    Do not infer renames, compatibility, behavioral changes or migrations
    from text identity. Never return source bodies or execute either project.
    """
    _, before = inspect_archive(_read_zip(original), original_sha256)
    _, after = inspect_archive(_read_zip(revised), revised_sha256)
    first = before["source_manifest"]["files"]
    second = after["source_manifest"]["files"]
    first_names, second_names = set(first), set(second)
    added = sorted(second_names - first_names)
    removed = sorted(first_names - second_names)
    modified = sorted(name for name in first_names & second_names if first[name] != second[name])
    unchanged = len(first_names & second_names) - len(modified)
    def row(name: str) -> dict[str, Any]:
        return {"path": name, "before_sha256": first.get(name), "after_sha256": second.get(name)}

    old_inspection, new_inspection = before["project_inspection"], after["project_inspection"]
    old_effects = old_inspection.get("applied", {})
    new_effects = new_inspection.get("applied", {})
    effect_comparable = (old_inspection["tuning"] == new_inspection["tuning"] == "verified"
                         and old_inspection["native_template"] == new_inspection["native_template"] == "verified"
                         and old_inspection["playable_modes"] == new_inspection["playable_modes"])
    effects = None
    if effect_comparable:
        effects = [{"effect": name, "before": old_effects.get(name), "after": new_effects.get(name)}
                   for name in sorted(set(old_effects) | set(new_effects))
                   if old_effects.get(name) != new_effects.get(name)]
    return {
        "schema": "skeleton.gameforge.portable_source_comparison.v1",
        "before_manifest_sha256": before["source_manifest"]["sha256"],
        "after_manifest_sha256": after["source_manifest"]["sha256"],
        "before_archive_sha256": before["archive_sha256"],
        "after_archive_sha256": after["archive_sha256"],
        "source_identical": not (added or removed or modified),
        "counts": {"added": len(added), "removed": len(removed),
                   "modified": len(modified), "unchanged": unchanged},
        "added": [row(name) for name in added],
        "removed": [row(name) for name in removed],
        "modified": [row(name) for name in modified],
        "before_project": old_inspection,
        "after_project": new_inspection,
        "native_effects_comparable": effect_comparable,
        "native_effect_changes": effects,
        "native_execution_qualified": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--output", type=Path, help="New directory under a trusted local parent")
    parser.add_argument("--require-current-template", action="store_true",
                        help="Refuse historical or inconsistent native projects before reopening")
    parser.add_argument("--compare-zip", type=Path, help="Compare against a second independently verified ZIP")
    parser.add_argument("--compare-sha256", help="Full separately retained manifest identity of the second ZIP")
    args = parser.parse_args(argv)
    if bool(args.compare_zip) != bool(args.compare_sha256):
        parser.error("--compare-zip and --compare-sha256 must be provided together")
    if args.compare_zip is not None and (args.output is not None or args.require_current_template):
        parser.error("comparison is read-only and cannot be combined with reopening or strict template gating")
    try:
        if args.compare_zip is not None:
            result = compare_archives(args.archive, args.expected_sha256,
                                      args.compare_zip, args.compare_sha256)
        else:
            result = reopen_archive(args.archive, args.expected_sha256, args.output,
                                    require_current_template=args.require_current_template)
    except PortableSourceError as exc:
        print(f"Portable source refused: {exc}", file=sys.stderr)
        return 2
    except OSError:
        print("Portable source I/O failed; an attempted new output may be incomplete", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
