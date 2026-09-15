#!/usr/bin/env python3
"""Rewrite retired Emergent chat imports to the local provider facade.

This is intentionally a narrow, idempotent migration utility. It changes only
imports of the exact retired module and leaves ``backend/server.py`` untouched
because that file has a separately audited boot-compatibility exception.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
RETIRED = "emergentintegrations.llm.chat"
REPLACEMENT = "core.ai_provider_compat"
EXCLUDED = {
    BACKEND / "server.py",
    BACKEND / "core" / "ai_provider.py",
    BACKEND / "core" / "ai_provider_compat.py",
}


def migrate() -> list[Path]:
    changed: list[Path] = []
    for path in sorted(BACKEND.rglob("*.py")):
        if path in EXCLUDED or any(part in {"tests", "__pycache__", ".venv", "venv"} for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8")
        if RETIRED not in text:
            continue
        updated = text.replace(RETIRED, REPLACEMENT)
        if updated != text:
            path.write_text(updated, encoding="utf-8")
            changed.append(path.relative_to(ROOT))
    return changed


def remaining() -> list[Path]:
    hits: list[Path] = []
    for path in sorted(BACKEND.rglob("*.py")):
        if path in EXCLUDED or any(part in {"tests", "__pycache__", ".venv", "venv"} for part in path.parts):
            continue
        try:
            if RETIRED in path.read_text(encoding="utf-8"):
                hits.append(path.relative_to(ROOT))
        except UnicodeError:
            continue
    return hits


def main() -> int:
    changed = migrate()
    for path in changed:
        print(f"migrated: {path}")
    leftovers = remaining()
    if leftovers:
        for path in leftovers:
            print(f"unmigrated: {path}")
        return 1
    print(f"legacy-llm-import-migration: OK ({len(changed)} files changed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
