#!/usr/bin/env python3
"""Preflight the exact Git ZIP before Windows creates files in the installer payload.

Git paths may be legal on Linux while being invalid, ambiguous, or unextractable
on Windows. Expand-Archive must not be the first component to discover this.
The limits match the installer payload contract (190 relative units, 180 per
component); both UTF-8 and UTF-16 counts matter across supported filesystems.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import stat
import sys
import unicodedata
import zipfile

MAX_RELATIVE_PATH = 190
MAX_COMPONENT = 180
MAX_ENTRIES = 150_000
MAX_SINGLE_FILE_BYTES = 1024**3
MAX_UNCOMPRESSED_BYTES = 8 * 1024**3
INVALID_WINDOWS = re.compile(r'[<>:"\\|?*\x00-\x1f\x7f-\x9f]')
RESERVED_WINDOWS = re.compile(
    r"^(?:CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|CLOCK\$|COM[1-9¹²³]|LPT[1-9¹²³])(?:\..*)?$",
    re.IGNORECASE,
)


def _utf16_units(value: str) -> int:
    return len(value.encode("utf-16-le", errors="strict")) // 2


def _lengths(value: str) -> tuple[int, int]:
    return (len(value.encode("utf-8", errors="strict")), _utf16_units(value))


def filename_errors(name: str) -> list[str]:
    """Validate a ZIP entry's portable, relative destination name."""
    errors: list[str] = []
    if not name:
        return ["archive entry has an empty name"]
    if name.startswith("/"):
        errors.append("absolute archive entry path")
    if "\\" in name:
        errors.append("backslash in archive entry path")
    # ZIP directory entries end in exactly one slash.
    relative = name[:-1] if name.endswith("/") else name
    try:
        utf8_size, utf16_size = _lengths(relative)
    except UnicodeError:
        return errors + ["nonportable Unicode archive entry path"]
    if max(utf8_size, utf16_size) > MAX_RELATIVE_PATH:
        errors.append(
            f"relative path exceeds {MAX_RELATIVE_PATH} units "
            f"({utf8_size} UTF-8 bytes / {utf16_size} UTF-16 units)"
        )

    for component in relative.split("/"):
        if not component or component in {".", ".."}:
            errors.append("empty/dot/dot-dot path component")
            continue
        if INVALID_WINDOWS.search(component):
            errors.append("Windows-invalid character")
        if component.endswith((" ", ".")):
            errors.append("trailing space/dot")
        if RESERVED_WINDOWS.fullmatch(component):
            errors.append("reserved Windows device name")
        if component.casefold() == ".git":
            errors.append("reserved Git metadata directory")
        if any(
            0x202A <= ord(char) <= 0x202E or 0x2066 <= ord(char) <= 0x2069
            for char in component
        ):
            errors.append("bidirectional control character")
        try:
            byte_count, unit_count = _lengths(component)
        except UnicodeError:
            errors.append("nonportable Unicode path component")
            continue
        if byte_count > MAX_COMPONENT or unit_count > MAX_COMPONENT:
            errors.append(f"component exceeds {MAX_COMPONENT}-unit budget")
    return errors


def archive_errors(entries: list[zipfile.ZipInfo]) -> list[str]:
    """Inspect central-directory metadata without extracting any member."""
    errors: list[str] = []
    nodes: dict[tuple[str, ...], tuple[str, str]] = {}
    seen_files: set[str] = set()
    total_bytes = 0
    if not entries:
        return ["ZIP contains no entries"]
    if len(entries) > MAX_ENTRIES:
        errors.append(f"ZIP exceeds {MAX_ENTRIES} entries")
        # Do not process an unbounded archive after a hard entry-count violation.
        return errors

    for entry in entries:
        name = entry.filename
        problems = filename_errors(name)
        errors.extend(f"{name!r}: {problem}" for problem in problems)
        if entry.flag_bits & 1:
            errors.append(f"{name!r}: encrypted ZIP entry not supported")
        if stat.S_IFMT(entry.external_attr >> 16) == stat.S_IFLNK:
            errors.append(f"{name!r}: symbolic link not supported in Windows payload")
        if entry.file_size > MAX_SINGLE_FILE_BYTES:
            errors.append(f"{name!r}: single file exceeds {MAX_SINGLE_FILE_BYTES} bytes")
        total_bytes += entry.file_size
        if problems:
            continue

        is_directory = name.endswith("/")
        relative = name[:-1] if is_directory else name
        parts = relative.split("/")
        if not is_directory:
            if relative in seen_files:
                errors.append(f"{name!r}: duplicate ZIP file entry")
            seen_files.add(relative)
        canonical = tuple(unicodedata.normalize("NFC", part.casefold()) for part in parts)
        for depth in range(1, len(parts) + 1):
            identity = canonical[:depth]
            display = "/".join(parts[:depth])
            kind = "directory" if depth < len(parts) or is_directory else "file"
            previous = nodes.setdefault(identity, (display, kind))
            if previous != (display, kind):
                errors.append(
                    f"{display!r}: portable checkout collision with "
                    f"{previous[0]!r} ({previous[1]} versus {kind})"
                )

    if total_bytes > MAX_UNCOMPRESSED_BYTES:
        errors.append(f"ZIP payload exceeds {MAX_UNCOMPRESSED_BYTES} uncompressed bytes")
    return sorted(set(errors))


def inspect_zip(path: Path) -> tuple[int, int, list[str]]:
    with zipfile.ZipFile(path, mode="r") as archive:
        entries = archive.infolist()
        return (
            len(entries),
            sum(entry.file_size for entry in entries),
            archive_errors(entries),
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        count, total_bytes, errors = inspect_zip(args.archive)
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile, ValueError) as exc:
        print(f"Windows payload ZIP preflight failed: {type(exc).__name__}", file=sys.stderr)
        return 2
    if errors:
        print(f"Windows payload ZIP rejected: {len(errors)} issue(s)", file=sys.stderr)
        for issue in errors[:50]:
            print(f"  - {issue}", file=sys.stderr)
        if len(errors) > 50:
            print(f"  - ... and {len(errors) - 50} further issue(s)", file=sys.stderr)
        return 1
    print(f"Windows payload ZIP safe: {count} entries, {total_bytes} uncompressed bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
