"""Migration bookkeeping (port of ``migration-plan.mjs``).

Applied files are keyed by BASENAME, so the same file applies once no matter
which directory it was globbed from (e.g. copying ``migrations/auth/0001.sql``
up into ``migrations/`` will not re-run it). Subdirectories are not descended.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True, order=True)
class Migration:
    name: str
    path: str


def migration_name(path: str) -> str:
    return path.replace("\\", "/").rsplit("/", 1)[-1]


def is_migration_file(path: str) -> bool:
    return path.endswith(".sql")


def pending_migrations(paths: Iterable[str], applied: Iterable[str]) -> list[Migration]:
    """Migrations in ``paths`` not yet in ``applied``, in apply (name) order."""
    done = set(applied)
    items = sorted(
        Migration(migration_name(p), p) for p in paths if is_migration_file(p)
    )
    seen: set[str] = set()
    out: list[Migration] = []
    for m in items:
        if m.name in done or m.name in seen:
            continue
        seen.add(m.name)
        out.append(m)
    return out


def scan_dir(directory: str | Path) -> list[str]:
    """Top-level ``.sql`` files in ``directory`` (no recursion), as strings."""
    d = Path(directory)
    if not d.is_dir():
        return []
    return [str(p) for p in d.iterdir() if p.is_file() and is_migration_file(p.name)]


def duplicate_basenames(paths: Iterable[str]) -> dict[str, list[str]]:
    """Basenames that appear under more than one path (a likely copy collision)."""
    by_name: dict[str, list[str]] = {}
    for p in paths:
        if is_migration_file(p):
            by_name.setdefault(migration_name(p), []).append(p)
    return {k: sorted(v) for k, v in by_name.items() if len(v) > 1}
