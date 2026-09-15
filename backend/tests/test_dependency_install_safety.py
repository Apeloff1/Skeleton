from __future__ import annotations

import json
from pathlib import Path

from scripts.check_dependency_install_safety import (
    install_command_violations,
    package_script_violations,
)


def _package(tmp_path: Path, scripts: dict[str, str]) -> Path:
    path = tmp_path / "package.json"
    path.write_text(json.dumps({"scripts": scripts}), encoding="utf-8")
    return path


def test_accepts_reviewed_postinstall_only(tmp_path: Path) -> None:
    path = _package(
        tmp_path,
        {"postinstall": "node ./scripts/patch-node-modules.js"},
    )
    assert package_script_violations(path) == []


def test_rejects_arbitrary_postinstall(tmp_path: Path) -> None:
    path = _package(tmp_path, {"postinstall": "node scripts/download-and-run.js"})
    findings = package_script_violations(path)
    assert any("unapproved postinstall" in finding for finding in findings)


def test_rejects_preinstall_execution(tmp_path: Path) -> None:
    path = _package(
        tmp_path,
        {
            "preinstall": "node scripts/bootstrap.js",
            "postinstall": "node ./scripts/patch-node-modules.js",
        },
    )
    findings = package_script_violations(path)
    assert any("unapproved preinstall" in finding for finding in findings)


def test_rejects_yarn_install_with_lifecycle_scripts_enabled(tmp_path: Path) -> None:
    path = tmp_path / "ci.yml"
    findings = install_command_violations(path, "run: yarn install --frozen-lockfile\n")
    assert any("--ignore-scripts" in finding for finding in findings)


def test_accepts_yarn_install_with_ignore_scripts(tmp_path: Path) -> None:
    path = tmp_path / "ci.yml"
    findings = install_command_violations(
        path,
        "run: yarn install --frozen-lockfile --ignore-scripts\n",
    )
    assert findings == []


def test_rejects_explicitly_negated_ignore_scripts(tmp_path: Path) -> None:
    path = tmp_path / "Dockerfile"
    findings = install_command_violations(
        path,
        "RUN yarn install --ignore-scripts=false\n",
    )
    assert any("--ignore-scripts" in finding for finding in findings)


def test_accepts_continued_install_command_with_ignore_scripts(tmp_path: Path) -> None:
    path = tmp_path / "Dockerfile"
    findings = install_command_violations(
        path,
        "RUN yarn install --frozen-lockfile \\\n    --ignore-scripts\n",
    )
    assert findings == []
