"""Index repository-root sprawl that belongs on Track E."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

ROOT_TEST_SUFFIXES = ("_test.py",)
ROOT_TEST_PREFIXES = ("test_",)
FORBIDDEN_ROOT_NAMES = {
    "test_result.md",
    "backend_test.py",
}
BAK_MARKERS = (".bak", ".bak_")
ARCHIVE_LANES = (
    "tests/legacy_root",
    "scripts/archive_root_tests",
)
SEVEN_BY_PREFIX = "SEVEN_BY_"


class RootSprawlIndex:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def root_entries(self) -> list[Path]:
        if not self.root.is_dir():
            return []
        return sorted(path for path in self.root.iterdir() if path.is_file())

    def stray_root_tests(self) -> list[Path]:
        found: list[Path] = []
        for path in self.root_entries():
            name = path.name
            if name in FORBIDDEN_ROOT_NAMES:
                found.append(path)
                continue
            if name.endswith(ROOT_TEST_SUFFIXES) or name.startswith(ROOT_TEST_PREFIXES):
                if name.endswith(".py"):
                    found.append(path)
        return found

    def stray_bak(self) -> list[Path]:
        found: list[Path] = []
        for path in self.root_entries():
            name = path.name
            if name.endswith(".bak") or ".bak_" in name:
                found.append(path)
        return found

    def seven_by_root(self) -> list[Path]:
        return [path for path in self.root_entries() if path.name.startswith(SEVEN_BY_PREFIX)]

    def archive_lanes_present(self) -> dict[str, bool]:
        return {lane: (self.root / lane).is_dir() for lane in ARCHIVE_LANES}

    def violations(self, *, include_seven_by: bool = False) -> list[Path]:
        items = [*self.stray_root_tests(), *self.stray_bak()]
        if include_seven_by:
            items.extend(self.seven_by_root())
        seen: set[Path] = set()
        out: list[Path] = []
        for item in items:
            if item not in seen:
                seen.add(item)
                out.append(item)
        return out

    def names(self, paths: Iterable[Path]) -> list[str]:
        return [path.name for path in paths]
