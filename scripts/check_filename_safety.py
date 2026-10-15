#!/usr/bin/env python3
"""Reject unsafe *new* repository filenames and ambiguous checkout paths.

Validates the entire prospective Git tree for case/Unicode collisions, while
grandfathering pre-existing long historical snapshot paths. Do not rename or
delete archived evidence simply to satisfy a new-file hygiene check.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import unicodedata

# Leave headroom for a checkout root such as C:\\work\\Skeleton on Windows.
MAX_NEW_PATH_LENGTH = 240
MAX_COMPONENT_BYTES = 240
INVALID_WINDOWS_CHARACTERS = re.compile(r'[<>:"\\|?*\x00-\x1f]')
RESERVED_WINDOWS_NAMES = re.compile(r"^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?$", re.I)


def _identity(part: str) -> str:
    return unicodedata.normalize("NFC", unicodedata.normalize("NFC", part).casefold())


def tree_paths(ref: str) -> set[str]:
    """Read the exact committed tree, independent of the runner's checkout FS."""
    completed = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", "-z", ref],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return {
        raw.decode("utf-8", errors="surrogateescape")
        for raw in completed.stdout.split(b"\x00")
        if raw
    }


def unsafe_filename(path: str) -> list[str]:
    """Return portability failures for a newly added/renamed path."""
    errors: list[str] = []
    try:
        path.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        return [f"{path!r}: path is not valid UTF-8"]
    if not path or len(path) > MAX_NEW_PATH_LENGTH:
        errors.append(f"{path!r}: exceeds {MAX_NEW_PATH_LENGTH} character portable path limit")
    for component in path.split("/"):
        if not component or component in {".", ".."}:
            errors.append(f"{path!r}: empty or relative path component")
            continue
        if INVALID_WINDOWS_CHARACTERS.search(component):
            errors.append(f"{path!r}: character unsupported by Windows")
        if component.endswith((" ", ".")):
            errors.append(f"{path!r}: component ends with space or dot")
        if RESERVED_WINDOWS_NAMES.fullmatch(component):
            errors.append(f"{path!r}: reserved Windows device filename")
        if len(component.encode("utf-8")) > MAX_COMPONENT_BYTES:
            errors.append(f"{path!r}: component exceeds {MAX_COMPONENT_BYTES} UTF-8 bytes")
    return errors


def check_paths(previous: set[str], current: set[str]) -> list[str]:
    """Check new paths plus every full-tree normalized path and ancestor."""
    errors: set[str] = set()
    for path in current - previous:
        errors.update(unsafe_filename(path))

    # Detect case-only and Unicode-equivalent *directory* collisions too:
    # Foo/a.py vs foo/b.py is unsafe even though no leaf names are equal.
    nodes: dict[tuple[str, ...], tuple[str, str]] = {}
    for path in sorted(current):
        components = path.split("/")
        for index in range(1, len(components) + 1):
            prefix = "/".join(components[:index])
            identity = tuple(_identity(p) for p in components[:index])
            kind = "file" if index == len(components) else "directory"
            existing = nodes.get(identity)
            if existing is None:
                nodes[identity] = (prefix, kind)
            elif existing != (prefix, kind):
                errors.add(
                    "case/Unicode filename collision: "
                    f"{existing[0]!r} ({existing[1]}) versus {prefix!r} ({kind})"
                )
    return sorted(errors)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="Baseline Git commit/ref")
    parser.add_argument("--head", required=True, help="Proposed Git commit/ref")
    args = parser.parse_args()

    try:
        previous = tree_paths(args.base)
        current = tree_paths(args.head)
    except subprocess.CalledProcessError as exc:
        print(f"filename-safety: cannot read Git tree: {exc}", file=sys.stderr)
        return 2

    failures = check_paths(previous, current)
    if failures:
        print(f"filename-safety: rejected ({len(failures)} finding(s))", file=sys.stderr)
        for issue in failures[:100]:
            print(f"  - {issue}", file=sys.stderr)
        if len(failures) > 100:
            print(f"  - ... plus {len(failures) - 100} additional findings", file=sys.stderr)
        return 1

    print(
        f"filename-safety: OK ({len(current)} committed paths, "
        f"{len(current - previous)} new/renamed paths)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
