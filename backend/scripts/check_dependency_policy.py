"""Enforce reproducible dependency declarations before vulnerability auditing."""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
PYTHON_REQUIREMENTS = ROOT / "backend" / "requirements.txt"
FRONTEND_PACKAGE = ROOT / "frontend" / "package.json"
FRONTEND_LOCK = ROOT / "frontend" / "yarn.lock"
_PY_EXACT_RE = re.compile(
    r"^[A-Za-z0-9_.-]+(?:\[[^\]]+\])?==(?P<version>[^\s;]+)(?:\s*;.*)?$"
)
_MUTABLE_JS_PREFIXES = (
    "git+",
    "git://",
    "git+ssh://",
    "ssh://",
    "http://",
    "https://",
    "file:",
    "link:",
    "workspace:",
    "github:",
    "gitlab:",
    "bitbucket:",
)
_MUTABLE_JS_VALUES = {"*", "latest", "next", "beta", "alpha", "canary"}
_PACKAGE_MANAGER_RE = re.compile(r"^yarn@[^+\s]+\+sha512\.[0-9a-fA-F]{128}$")


def python_violations(path: Path = PYTHON_REQUIREMENTS) -> list[str]:
    findings: list[str] = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("-"):
            findings.append(
                f"{path.name}:{number}: requirements directives/includes are forbidden in the production manifest: {line}"
            )
            continue
        match = _PY_EXACT_RE.fullmatch(line)
        if not match:
            findings.append(f"{path.name}:{number}: production dependency is not exact-pinned: {line}")
            continue
        version = match.group("version")
        if "*" in version:
            findings.append(f"{path.name}:{number}: wildcard version is not an exact pin: {line}")
    return findings


def frontend_violations(package_path: Path = FRONTEND_PACKAGE, lock_path: Path = FRONTEND_LOCK) -> list[str]:
    findings: list[str] = []
    if not lock_path.exists() or lock_path.stat().st_size == 0:
        findings.append("frontend/yarn.lock: required non-empty lockfile is missing")

    package = json.loads(package_path.read_text(encoding="utf-8"))
    manager = str(package.get("packageManager", "")).strip()
    if not _PACKAGE_MANAGER_RE.fullmatch(manager):
        findings.append("frontend/package.json: packageManager must pin Yarn with a full sha512 integrity hash")

    for section in ("dependencies", "devDependencies", "optionalDependencies"):
        for name, raw_value in sorted(package.get(section, {}).items()):
            value = str(raw_value).strip()
            lowered = value.lower()
            if lowered in _MUTABLE_JS_VALUES:
                findings.append(f"frontend/package.json: {section}.{name} uses mutable version {value!r}")
            if lowered.startswith(_MUTABLE_JS_PREFIXES):
                findings.append(f"frontend/package.json: {section}.{name} uses non-registry source {value!r}")
    return findings


def main() -> int:
    findings = python_violations() + frontend_violations()
    if findings:
        print("Dependency declaration policy violations detected:", file=sys.stderr)
        for finding in findings:
            print(f"  - {finding}", file=sys.stderr)
        return 1
    print("Dependency policy passed: Python exact pins and frontend lock/integrity constraints verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
