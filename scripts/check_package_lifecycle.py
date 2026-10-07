#!/usr/bin/env python3
"""Reject unreviewed package-manager lifecycle hooks in active tracked manifests."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LIFECYCLE_NAMES = {
    "preinstall",
    "install",
    "postinstall",
    "prepare",
    "prepublish",
    "prepublishOnly",
}

ALLOWED = {
    ("frontend/package.json", "postinstall"): "node ./scripts/patch-node-modules.js",
}

# Historical branch snapshots are inert repository records, not installable
# package roots. Scanning their package.json lifecycle hooks makes current PRs
# fail on commands inherited from archived branches even though CI never
# installs dependencies from these paths. Keep this exclusion deliberately
# narrow: every other tracked package.json remains fail-closed.
EXCLUDED_MANIFEST_PREFIXES = (
    "satellites/branch-snapshots/",
)


def tracked_package_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO_ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return [
        entry.decode("utf-8", errors="surrogateescape")
        for entry in result.stdout.split(b"\0")
        if entry and entry.decode("utf-8", errors="surrogateescape").endswith("package.json")
    ]


def manifest_is_in_scope(package_file: str) -> bool:
    return not any(
        package_file.startswith(prefix) for prefix in EXCLUDED_MANIFEST_PREFIXES
    )


def violations() -> list[str]:
    findings: list[str] = []
    for package_file in tracked_package_files():
        if not manifest_is_in_scope(package_file):
            continue

        path = REPO_ROOT / package_file
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            findings.append(f"{package_file}: cannot safely parse manifest: {exc}")
            continue

        if not isinstance(payload, dict):
            findings.append(f"{package_file}: manifest root must be an object")
            continue

        scripts = payload.get("scripts", {})
        if not isinstance(scripts, dict):
            findings.append(f"{package_file}: scripts must be an object")
            continue

        for name in sorted(LIFECYCLE_NAMES):
            if name not in scripts:
                continue
            command = scripts[name]
            if not isinstance(command, str):
                findings.append(f"{package_file}: lifecycle hook {name!r} must be a string")
                continue
            if ALLOWED.get((package_file, name)) != command:
                findings.append(f"{package_file}: unapproved lifecycle hook {name!r}")
    return findings


def main() -> int:
    findings = violations()
    if findings:
        for finding in findings:
            print(finding)
        return 1
    print("package lifecycle policy: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
