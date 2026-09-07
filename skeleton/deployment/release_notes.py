"""Release notes — automated changelog generation from commit metadata.

Aggregates changes by subsystem and type (feature, fix, security,
breaking), generates formatted release notes per version, tracks
release trains, and flags breaking changes requiring migration notes.
Integrates with the audit log for release publication events.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


CATEGORIES = ["feature", "fix", "security", "performance", "breaking", "docs", "chore"]


@dataclass
class ChangeEntry:
    subsystem: str
    category: str
    summary: str
    author: str = "system"
    commit: str = ""
    timestamp_ns: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "subsystem": self.subsystem,
            "category": self.category,
            "summary": self.summary,
            "author": self.author,
            "commit": self.commit,
        }


@dataclass
class Release:
    version: str
    entries: List[ChangeEntry] = field(default_factory=list)
    published: bool = False
    published_ns: int = 0

    def breaking_changes(self) -> List[ChangeEntry]:
        return [e for e in self.entries if e.category == "breaking"]


class ReleaseNotesGenerator:
    """Changelog aggregation and release note rendering."""

    def __init__(self):
        self._pending: List[ChangeEntry] = []
        self._releases: Dict[str, Release] = {}

    def add(self, subsystem: str, category: str, summary: str,
            author: str = "system", commit: str = "") -> ChangeEntry:
        if category not in CATEGORIES:
            category = "chore"
        entry = ChangeEntry(subsystem=subsystem, category=category, summary=summary,
                            author=author, commit=commit, timestamp_ns=time.time_ns())
        self._pending.append(entry)
        return entry

    def cut_release(self, version: str) -> Release:
        release = Release(version=version, entries=list(self._pending))
        self._pending.clear()
        self._releases[version] = release
        return release

    def render(self, version: str, format: str = "markdown") -> str:
        release = self._releases.get(version)
        if not release:
            return f"# Release {version}\n\nNo changes recorded.\n"
        by_cat: Dict[str, List[ChangeEntry]] = {}
        for e in release.entries:
            by_cat.setdefault(e.category, []).append(e)
        lines = [f"# Release {version}", ""]
        breaking = release.breaking_changes()
        if breaking:
            lines.append("## ⚠ Breaking Changes")
            lines.append("")
            for e in breaking:
                lines.append(f"- **[{e.subsystem}]** {e.summary} ({e.commit or 'no-commit'})")
            lines.append("")
        for cat in ["feature", "fix", "security", "performance", "docs", "chore"]:
            entries = by_cat.get(cat, [])
            if not entries:
                continue
            lines.append(f"## {cat.capitalize()}s" if not cat.endswith("s") else f"## {cat.capitalize()}")
            lines.append("")
            for e in entries:
                lines.append(f"- **[{e.subsystem}]** {e.summary}")
            lines.append("")
        return "\n".join(lines)

    def publish(self, version: str) -> Dict[str, Any]:
        release = self._releases.get(version)
        if not release:
            return {"published": False, "reason": "not found"}
        release.published = True
        release.published_ns = time.time_ns()
        return {"published": True, "version": version, "entries": len(release.entries)}

    def requires_migration_notes(self, version: str) -> bool:
        release = self._releases.get(version)
        return bool(release and release.breaking_changes())

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "release-notes-card",
            "pending_entries": len(self._pending),
            "releases": {
                v: {"entries": len(r.entries), "published": r.published, "breaking": len(r.breaking_changes())}
                for v, r in self._releases.items()
            },
        }
