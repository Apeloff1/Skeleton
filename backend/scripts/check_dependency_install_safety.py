"""Fail CI when dependency restore can execute unreviewed package lifecycle code.

Dependency installation is an execution boundary: npm/yarn/pnpm packages may run
preinstall/install/postinstall hooks before vulnerability scanners get a chance
to inspect the resolved graph. Repository CI and image builds therefore restore
JavaScript dependencies with lifecycle scripts disabled, then explicitly invoke
only the reviewed repository-owned hardening hook.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_PACKAGE = REPO_ROOT / "frontend" / "package.json"
APPROVED_LIFECYCLE_SCRIPTS = {
    "postinstall": "node ./scripts/patch-node-modules.js",
}
INSTALL_LIFECYCLE_KEYS = ("preinstall", "install", "postinstall")
INSTALL_COMMAND_RE = re.compile(
    r"\b(?:yarn(?:\s+--cwd\s+[^\s]+)?\s+(?:install|add)|"
    r"npm\s+(?:ci|install)|pnpm\s+(?:install|add))\b",
    re.IGNORECASE,
)
IGNORE_SCRIPTS_RE = re.compile(r"(?:^|\s)--ignore-scripts(?:\s|$|\\)")
NEGATED_IGNORE_RE = re.compile(r"--ignore-scripts\s*=\s*(?:false|0)\b", re.IGNORECASE)


def operational_files() -> Iterable[Path]:
    workflow_dir = REPO_ROOT / ".github" / "workflows"
    yield from sorted(workflow_dir.glob("*.yml"))
    yield from sorted(workflow_dir.glob("*.yaml"))

    for path in sorted(REPO_ROOT.rglob("Dockerfile*")):
        if any(part in {".git", ".venv", "venv", "node_modules", "dist", "build"} for part in path.parts):
            continue
        if path.is_file():
            yield path


def package_script_violations(path: Path = FRONTEND_PACKAGE) -> list[str]:
    try:
        package = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return [f"{path}: unable to validate package lifecycle scripts: {exc}"]

    scripts = package.get("scripts", {})
    if not isinstance(scripts, dict):
        return [f"{path}: package scripts must be a mapping"]

    findings: list[str] = []
    for key in INSTALL_LIFECYCLE_KEYS:
        if key not in scripts:
            continue
        value = scripts[key]
        approved = APPROVED_LIFECYCLE_SCRIPTS.get(key)
        if value != approved:
            findings.append(
                f"{path.name}: unapproved {key} lifecycle script; dependency restore must not execute arbitrary repository commands"
            )

    approved_postinstall = APPROVED_LIFECYCLE_SCRIPTS["postinstall"]
    if scripts.get("postinstall") != approved_postinstall:
        findings.append(
            f"{path.name}: postinstall must remain exactly {approved_postinstall!r}"
        )
    return findings


def _command_window(lines: list[str], index: int) -> str:
    """Return a small logical command window for folded/continued install commands."""
    parts = [lines[index].strip()]
    for offset in range(1, 4):
        pos = index + offset
        if pos >= len(lines):
            break
        previous = parts[-1]
        current = lines[pos].strip()
        if previous.endswith("\\") or previous in {"run: |", "run: |-", "run: >", "run: >-"}:
            parts.append(current)
            continue
        if current.startswith(("--", "&&", "\\")):
            parts.append(current)
            continue
        break
    return " ".join(parts)


def install_command_violations(path: Path, text: str) -> list[str]:
    findings: list[str] = []
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if not INSTALL_COMMAND_RE.search(line):
            continue
        command = _command_window(lines, index)
        if NEGATED_IGNORE_RE.search(command) or not IGNORE_SCRIPTS_RE.search(command):
            findings.append(
                f"{path.name}:{index + 1}: dependency install must disable lifecycle scripts with --ignore-scripts"
            )
    return findings


def file_violations(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return [f"{path}: read failure: {exc}"]
    return install_command_violations(path, text)


def main() -> int:
    findings = package_script_violations()
    scanned = 0
    for path in operational_files():
        scanned += 1
        findings.extend(file_violations(path))

    patch_script = REPO_ROOT / "frontend" / "scripts" / "patch-node-modules.js"
    if not patch_script.is_file():
        findings.append("frontend/scripts/patch-node-modules.js: approved postinstall target missing")

    if findings:
        print("Dependency installation safety violations detected:", file=sys.stderr)
        for finding in sorted(set(findings)):
            print(f"  - {finding}", file=sys.stderr)
        return 1

    print(f"Dependency installation safety gate passed across {scanned} operational files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
