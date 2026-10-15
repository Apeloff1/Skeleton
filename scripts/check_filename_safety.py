#!/usr/bin/env python3
"""Reject unsafe *new* repository filenames and ambiguous checkout paths.

Validates the entire prospective Git tree for case/Unicode collisions, while
grandfathering unchanged historical paths and collisions. New aliases are blocked. Do not rename or
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
MAX_COMPONENT_BYTES = 180
MAX_COMPONENT_UTF16 = 180
INVALID_WINDOWS_CHARACTERS = re.compile(r'[<>:"\\|?*\x00-\x1f\x7f-\x9f]')
RESERVED_WINDOWS_NAMES = re.compile(r"^(?:CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|COM[1-9¹²³]|LPT[1-9¹²³]|CLOCK\$)(?:\..*)?$", re.I)


def _identity(part: str) -> str:
    return unicodedata.normalize("NFC", part.casefold())


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
        utf8_length = len(path.encode("utf-8", errors="strict"))
        utf16_length = len(path.encode("utf-16-le")) // 2
    except UnicodeEncodeError:
        return [f"{path!r}: path is not valid UTF-8"]
    # Git transports pathnames as UTF-8. Windows counts UTF-16 code units.
    # Bound both, since a UTF-16-only check misses long UTF-8 names on
    # byte-limited Linux, macOS and archive tooling.
    if not path or max(utf8_length, utf16_length) > MAX_NEW_PATH_LENGTH:
        errors.append(
            f"{path!r}: exceeds {MAX_NEW_PATH_LENGTH}-unit portable path limit "
            f"({utf8_length} UTF-8 bytes; {utf16_length} Windows UTF-16 units)"
        )
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
        if component.casefold() == ".git":
            errors.append(f"{path!r}: reserved Git metadata path")
        if any(0x202A <= ord(ch) <= 0x202E or 0x2066 <= ord(ch) <= 0x2069 for ch in component):
            errors.append(f"{path!r}: bidirectional control character in filename")
        if len(component.encode("utf-16-le")) // 2 > MAX_COMPONENT_UTF16:
            errors.append(f"{path!r}: component exceeds {MAX_COMPONENT_UTF16} UTF-16 code units")
        if len(component.encode("utf-8")) > MAX_COMPONENT_BYTES:
            errors.append(f"{path!r}: component exceeds {MAX_COMPONENT_BYTES} UTF-8 bytes")
    return errors


def _collisions(paths: set[str]) -> dict[tuple[str, ...], frozenset[tuple[str, str]]]:
    """Find ambiguous files AND directory prefixes, not only leaf filenames."""
    nodes: dict[tuple[str, ...], tuple[str, str]] = {}
    conflicts: dict[tuple[str, ...], set[tuple[str, str]]] = {}
    for path in sorted(paths):
        components = path.split("/")
        normalized = tuple(_identity(component) for component in components)
        for index in range(1, len(components) + 1):
            identity = normalized[:index]
            entry = ("/".join(components[:index]), "file" if index == len(components) else "directory")
            existing = nodes.setdefault(identity, entry)
            if existing != entry:
                conflicts.setdefault(identity, {existing}).add(entry)
    return {identity: frozenset(aliases) for identity, aliases in conflicts.items()}


def check_paths(previous: set[str], current: set[str]) -> list[str]:
    """Reject new unsafe paths while allowing unchanged historical collisions."""
    errors: set[str] = set()
    added = current - previous
    for path in added:
        errors.update(unsafe_filename(path))

    # The repository contains legacy snapshot trees with UI/ and ui/ prefixes.
    # Checking *all* current collisions without comparing the base would make
    # every unrelated PR fail. Never allow new aliases or paths into these
    # pre-existing ambiguous trees, however.
    old_collisions = _collisions(previous)
    new_collisions = _collisions(current)
    for identity, aliases in new_collisions.items():
        introduced = aliases - old_collisions.get(identity, frozenset())
        if introduced:
            paths = ", ".join(repr(prefix) + " (" + kind + ")" for prefix, kind in sorted(aliases))
            errors.add("case/Unicode filename collision: " + paths)

    ambiguous_prefixes = {
        prefix
        for aliases in new_collisions.values()
        for prefix, _kind in aliases
    }
    for path in added:
        if any(path == prefix or path.startswith(prefix + "/") for prefix in ambiguous_prefixes):
            errors.add(f"{path!r}: newly introduced path lies inside an ambiguous case/Unicode directory")

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
