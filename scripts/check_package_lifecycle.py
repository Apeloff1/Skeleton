#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
from pathlib import Path

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


def tracked_package_files() -> list[str]:
    output = subprocess.check_output(["git", "ls-files", "*package.json"], text=True)
    return [line for line in output.splitlines() if line]


def violations() -> list[str]:
    findings: list[str] = []
    for package_file in tracked_package_files():
        payload = json.loads(Path(package_file).read_text(encoding="utf-8"))
        scripts = payload.get("scripts", {})
        if not isinstance(scripts, dict):
            findings.append(f"{package_file}: scripts must be an object")
            continue
        for name in LIFECYCLE_NAMES:
            if name not in scripts:
                continue
            if ALLOWED.get((package_file, name)) != scripts[name]:
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
