#!/usr/bin/env python3
"""Fail if any versioned manifest drifts from the repo-root VERSION file.

VERSION is the single source of truth (semantic version, no leading "v").
Usage: python scripts/check_version_drift.py [--tag vX.Y.Z]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")


def _toml(rel: str) -> str:
    return tomllib.loads((ROOT / rel).read_text())["project"]["version"]


def _package_json(rel: str) -> str:
    return json.loads((ROOT / rel).read_text())["version"]


def _app_json(rel: str) -> str:
    return json.loads((ROOT / rel).read_text())["expo"]["version"]


MANIFESTS = {
    "pyproject.toml": _toml,
    "backend/pyproject.toml": _toml,
    "frontend/package.json": _package_json,
    "frontend/app.json": _app_json,
}


def read_version(root: Path = ROOT) -> str:
    return (root / "VERSION").read_text().strip()


def check(tag: str | None = None) -> list[str]:
    problems: list[str] = []
    version = read_version()
    if not SEMVER.match(version):
        problems.append(f"VERSION {version!r} is not a semantic version")
    for rel, reader in MANIFESTS.items():
        try:
            found = reader(rel)
        except (KeyError, FileNotFoundError, ValueError) as exc:
            problems.append(f"{rel}: cannot read version ({exc})")
            continue
        if found != version:
            problems.append(f"{rel}: version {found!r} != VERSION {version!r}")
    if tag is not None and tag.removeprefix("refs/tags/") != f"v{version}":
        problems.append(f"tag {tag!r} does not match VERSION (expected 'v{version}')")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag")
    args = ap.parse_args(argv)
    problems = check(args.tag)
    if problems:
        print("version drift:\n  - " + "\n  - ".join(problems), file=sys.stderr)
        return 1
    print(f"version OK: {read_version()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
