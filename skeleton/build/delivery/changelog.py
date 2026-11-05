"""Conventional-commit parsing and changelog rendering."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from skeleton.build.delivery.version import Version

_HEADER = re.compile(r"^(?P<type>[a-z]+)(?:\((?P<scope>[^()\s]{1,64})\))?(?P<bang>!)?: (?P<subject>.+)$")
SECTIONS = (
    ("breaking", "Breaking changes"),
    ("feat", "Features"),
    ("fix", "Fixes"),
    ("perf", "Performance"),
    ("revert", "Reverts"),
    ("other", "Other"),
)
HIDDEN_TYPES = frozenset({"chore", "ci", "style", "test", "docs", "build", "refactor"})


@dataclass(frozen=True)
class Change:
    sha: str
    type: str
    scope: str | None
    subject: str
    breaking: bool


def parse_commit(sha: str, message: str) -> Change | None:
    lines = message.strip().splitlines()
    if not lines:
        return None
    match = _HEADER.match(lines[0].strip())
    if not match:
        return Change(sha, "other", None, lines[0].strip(), False)
    breaking = bool(match["bang"]) or any(line.startswith(("BREAKING CHANGE:", "BREAKING-CHANGE:")) for line in lines[1:])
    return Change(sha, match["type"], match["scope"], match["subject"].strip(), breaking)


def required_bump(changes: Iterable[Change]) -> str | None:
    level = None
    for change in changes:
        if change.breaking:
            return "major"
        if change.type == "feat":
            level = "minor"
        elif change.type in ("fix", "perf", "revert") and level is None:
            level = "patch"
    return level


def next_version(current: str, changes: Iterable[Change]) -> Version:
    items = list(changes)
    version = Version.parse(current)
    bump = required_bump(items)
    if bump is None:
        return version
    if version.major == 0 and bump == "major":
        bump = "minor"  # 0.x: breaking changes bump minor
    return version.bump(bump)  # type: ignore[arg-type]


def group(changes: Iterable[Change]) -> dict[str, list[Change]]:
    out: dict[str, list[Change]] = {key: [] for key, _ in SECTIONS}
    for change in changes:
        if change.breaking:
            out["breaking"].append(change)
        elif change.type in out:
            out[change.type].append(change)
        elif change.type not in HIDDEN_TYPES:
            out["other"].append(change)
    return out


def render(version: Version | str, changes: Iterable[Change], *, date: str) -> str:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        raise ValueError("date must be YYYY-MM-DD")
    grouped = group(changes)
    lines = [f"## {version} ({date})", ""]
    for key, title in SECTIONS:
        items = grouped[key]
        if not items:
            continue
        lines.append(f"### {title}")
        lines.append("")
        for change in items:
            scope = f"**{change.scope}:** " if change.scope else ""
            lines.append(f"- {scope}{change.subject} ({change.sha[:7]})")
        lines.append("")
    if len(lines) == 2:
        lines.append("_No user-facing changes._")
        lines.append("")
    return "\n".join(lines)
