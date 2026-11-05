"""Conventional-commit parsing and changelog rendering."""

from __future__ import annotations

import re
import unicodedata
from datetime import date as calendar_date
from itertools import islice
from dataclasses import dataclass
from typing import Iterable

from skeleton.build.delivery.version import Version
from skeleton.build.delivery._util import DeliveryError

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
MAX_CHANGELOG_CHANGES = 8192


def _safe_markdown(text: str) -> str:
    # Commit subjects are untrusted. Prevent raw HTML and Markdown link syntax
    # from becoming active content in rendered release notes.
    return re.sub(r"([\\`*_{}\[\]()<>])", r"\\\1", text)


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
    if type(version) is str:
        version_text = str(Version.parse(version))
    elif type(version) is Version:
        version_text = str(version)
    else:
        raise DeliveryError("invalid changelog version")
    if not isinstance(date, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        raise DeliveryError("date must be YYYY-MM-DD")
    try:
        calendar_date.fromisoformat(date)
    except ValueError as exc:
        raise DeliveryError("invalid calendar date") from exc
    bounded = list(islice(changes, MAX_CHANGELOG_CHANGES + 1))
    if len(bounded) > MAX_CHANGELOG_CHANGES:
        raise DeliveryError("changelog change count exceeds bound")
    if any(not isinstance(c, Change) or not isinstance(c.sha, str)
           or not re.fullmatch(r"[0-9a-f]{7,40}", c.sha) for c in bounded):
        raise DeliveryError("invalid changelog commit evidence")
    for change in bounded:
        if (type(change.subject) is not str or not 1 <= len(change.subject) <= 512
                or type(change.type) is not str or not re.fullmatch(r"[a-z]{1,32}", change.type)
                or type(change.breaking) is not bool
                or (change.scope is not None and
                    (type(change.scope) is not str or not 1 <= len(change.scope) <= 64))
                or any(unicodedata.category(ch) in {"Cc", "Cf", "Zl", "Zp"}
                       for ch in change.subject + (change.scope or ""))):
            raise DeliveryError("invalid changelog subject or scope evidence")
    grouped = group(bounded)
    lines = [f"## {version_text} ({date})", ""]
    for key, title in SECTIONS:
        items = grouped[key]
        if not items:
            continue
        lines.append(f"### {title}")
        lines.append("")
        for change in items:
            scope = f"**{_safe_markdown(change.scope)}:** " if change.scope else ""
            lines.append(f"- {scope}{_safe_markdown(change.subject)} ({change.sha[:7]})")
        lines.append("")
    if len(lines) == 2:
        lines.append("_No user-facing changes._")
        lines.append("")
    return "\n".join(lines)
