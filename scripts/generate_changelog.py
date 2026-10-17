#!/usr/bin/env python3
"""Generate a Markdown changelog section from Conventional Commit subjects.

Usage:
  python scripts/generate_changelog.py --version 16.1.0 [--from v16.0.0] [--to HEAD]
Without --from, the most recent v* tag reachable from --to is used (or full history).
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import date

SECTIONS = (
    ("breaking", "Breaking changes"),
    ("feat", "Features"),
    ("fix", "Fixes"),
    ("perf", "Performance"),
    ("security", "Security"),
    ("ci", "CI / build"),
    ("docs", "Documentation"),
    ("other", "Other changes"),
)
_TYPE_MAP = {"feat": "feat", "fix": "fix", "perf": "perf", "security": "security", "sec": "security",
             "ci": "ci", "build": "ci", "docs": "docs"}
_CC = re.compile(r"^(?P<type>[a-zA-Z]+)(?:\((?P<scope>[^)]*)\))?(?P<bang>!)?:\s*(?P<desc>.+)$")
_SKIP = re.compile(r"^(Merge (branch|pull request)|Revert \"Revert)")


def classify(subject: str) -> tuple[str, str]:
    """Return (section key, rendered line) for one commit subject."""
    m = _CC.match(subject.strip())
    if not m:
        return "other", subject.strip()
    desc = m["desc"].strip()
    line = f"**{m['scope']}:** {desc}" if m["scope"] else desc
    if m["bang"]:
        return "breaking", line
    return _TYPE_MAP.get(m["type"].lower(), "other"), line


def render(version: str, subjects: list[str], when: date | None = None) -> str:
    buckets: dict[str, list[str]] = {k: [] for k, _ in SECTIONS}
    for s in subjects:
        if not s.strip() or _SKIP.match(s):
            continue
        key, line = classify(s)
        if line not in buckets[key]:
            buckets[key].append(line)
    out = [f"## v{version} ({(when or date.today()).isoformat()})", ""]
    for key, title in SECTIONS:
        if buckets[key]:
            out.append(f"### {title}")
            out.extend(f"- {line}" for line in buckets[key])
            out.append("")
    if len(out) == 2:
        out.extend(["_No changes._", ""])
    return "\n".join(out)


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout


def previous_tag(ref: str) -> str | None:
    try:
        return _git("describe", "--tags", "--abbrev=0", "--match", "v*", f"{ref}^").strip() or None
    except subprocess.CalledProcessError:
        return None


def subjects_between(start: str | None, end: str) -> list[str]:
    rng = f"{start}..{end}" if start else end
    return _git("log", "--no-merges", "--format=%s", rng).splitlines()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    ap.add_argument("--from", dest="start")
    ap.add_argument("--to", default="HEAD")
    args = ap.parse_args(argv)
    start = args.start or previous_tag(args.to)
    sys.stdout.write(render(args.version, subjects_between(start, args.to)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
