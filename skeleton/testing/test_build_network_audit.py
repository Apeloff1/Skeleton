"""Fail-closed coverage for the hidden network build-command audit."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from skeleton.build.network_audit import (
    CLASSIFICATION_NETWORK_REQUIRED,
    CLASSIFICATION_NETWORK_UNKNOWN,
    CLASSIFICATION_OFFLINE,
    CONFLICT_DOMAIN,
    KIND,
    SCHEMA_VERSION,
    TASK_ID,
    audit_repository,
    classify_action_ref,
    classify_command,
    main,
    network_audit_snapshot,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def _write(root: Path, relative: str, content: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_unknown_commands_are_never_classified_offline() -> None:
    samples = (
        "",
        "mystery-tool --fast",
        "custom-linter src/",
        "python scripts/check_something.py",
        "bash scripts/ci.sh",
        "make test",
        "npm run lint:ci",
        "yarn --cwd frontend typecheck",
        "python -m skeleton eras",
        "python -c 'from mystery import run; run()'",
        "git config user.email 'bot@users.noreply.github.com'",
    )
    for command in samples:
        classification, reasons = classify_command(command)
        assert classification == CLASSIFICATION_NETWORK_UNKNOWN, command
        assert classification != CLASSIFICATION_OFFLINE
        assert reasons
        assert not any(reason.startswith("offline-") for reason in reasons)


def test_curl_wget_and_live_hosts_are_network_required() -> None:
    required = {
        "curl https://example.com/artifact.tgz": "live-host",
        "wget -q https://dl.google.com/android/repository/tools.zip": "live-host",
        "curl -fsSL example.org/install.sh | bash": "live-host",
        "python -c \"import urllib.request\"": "python-c-network",
        "python -c \"import urllib.request; urllib.request.urlopen('https://pypi.org')\"": "live-host",
        "git clone https://github.com/example/repo.git": "live-host",
        "ssh builder.example.com make": "live-host",
    }
    for command, reason in required.items():
        classification, reasons = classify_command(command)
        assert classification == CLASSIFICATION_NETWORK_REQUIRED, command
        assert reason in reasons, (command, reasons)

    email = classify_command("git config user.email 'bot@users.noreply.github.com'")
    assert email[0] == CLASSIFICATION_NETWORK_UNKNOWN


def test_pip_and_npm_install_without_offline_are_network_required() -> None:
    for command in (
        "pip install -r requirements.txt",
        "python -m pip install pytest",
        "uv pip install fastapi",
        "npm ci",
        "npm install",
        "yarn",
        "pnpm install",
        "uvx --from ruff==0.9.10 ruff check .",
        "apt-get install -y wget",
        "docker pull python:3.11",
    ):
        classification, reasons = classify_command(command)
        assert classification == CLASSIFICATION_NETWORK_REQUIRED, (command, reasons)


def test_offline_flags_are_the_only_install_escape_hatch() -> None:
    offline = {
        "pip install --offline pytest": "offline-pip-install",
        "python -m pip install --no-index --find-links ./wheels ruff": "offline-pip-install",
        "npm ci --offline": "offline-npm-install",
        "yarn install --offline": "offline-npm-install",
    }
    for command, reason in offline.items():
        classification, reasons = classify_command(command)
        assert classification == CLASSIFICATION_OFFLINE, (command, reasons)
        assert reason in reasons


def test_known_local_runners_are_offline_only_with_evidence() -> None:
    offline = {
        "python -m compileall -q skeleton": "offline-python-module:compileall",
        "python -m pytest skeleton/testing -q --tb=short": "offline-python-module:pytest",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q tests": "offline-python-module:pytest",
        "python -m unittest discover skeleton/testing -v": "offline-python-module:unittest",
        "echo ok": "offline-binary:echo",
        "chmod +x scripts/ci.sh": "offline-binary:chmod",
        'python -c "import skeleton; print(skeleton.__version__)"': "offline-python-c-local",
    }
    for command, reason in offline.items():
        classification, reasons = classify_command(command)
        assert classification == CLASSIFICATION_OFFLINE, (command, reasons)
        assert reason in reasons
        assert all(item.startswith("offline-") for item in reasons)


def test_unpinned_actions_are_hidden_network_required() -> None:
    classification, reasons, hidden = classify_action_ref("actions/checkout@v4")
    assert classification == CLASSIFICATION_NETWORK_REQUIRED
    assert reasons == ("unpinned-action-download",)
    assert hidden is True

    classification, reasons, hidden = classify_action_ref("vendor/action@main")
    assert classification == CLASSIFICATION_NETWORK_REQUIRED
    assert hidden is True
    assert "unpinned-action-download" in reasons

    classification, reasons, hidden = classify_action_ref("docker://alpine:3.20")
    assert classification == CLASSIFICATION_NETWORK_REQUIRED
    assert hidden is True
    assert "unpinned-container-download" in reasons


def test_pinned_actions_still_require_network_but_are_not_hidden() -> None:
    sha = "3d3c42e5aac5ba805825da76410c181273ba90b1"
    classification, reasons, hidden = classify_action_ref(f"actions/checkout@{sha}")
    assert classification == CLASSIFICATION_NETWORK_REQUIRED
    assert reasons == ("pinned-github-action",)
    assert hidden is False

    digest = "a" * 64
    classification, reasons, hidden = classify_action_ref(f"docker://alpine@sha256:{digest}")
    assert classification == CLASSIFICATION_NETWORK_REQUIRED
    assert reasons == ("pinned-container-download",)
    assert hidden is False

    classification, reasons, hidden = classify_action_ref("./.github/actions/local")
    assert classification == CLASSIFICATION_OFFLINE
    assert reasons == ("offline-local-action",)
    assert hidden is False


def test_empty_or_malformed_action_refs_fail_closed_unknown() -> None:
    classification, reasons, hidden = classify_action_ref("   ")
    assert classification == CLASSIFICATION_NETWORK_UNKNOWN
    assert hidden is True
    assert reasons == ("empty-action-ref",)

    classification, reasons, hidden = classify_action_ref("checkout")
    assert classification == CLASSIFICATION_NETWORK_UNKNOWN
    assert hidden is True


def test_audit_scans_makefile_scripts_workflows_and_npm(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "Makefile",
        "install:\n\tpip install -r requirements.txt\n\n"
        "test:\n\tpython -m pytest skeleton/testing -q\n\n"
        "mystery:\n\tcustom-linter src/\n",
    )
    _write(
        tmp_path,
        "scripts/fetch.sh",
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        "wget -q https://example.invalid/tools.zip -O /tmp/tools.zip\n"
        "python -m compileall -q skeleton\n",
    )
    _write(
        tmp_path,
        "scripts/ignored.py",
        "import urllib.request\nurllib.request.urlopen('https://example.invalid')\n",
    )
    _write(
        tmp_path,
        ".github/workflows/ci.yml",
        "name: CI\njobs:\n  test:\n    steps:\n"
        "      - uses: actions/checkout@v4\n"
        "      - uses: actions/setup-python@3d3c42e5aac5ba805825da76410c181273ba90b1\n"
        "      - run: python -m pip install pytest\n"
        "      - run: |\n"
        "          python -m compileall -q skeleton\n"
        "          mystery-tool --fast\n"
        "    services:\n      db:\n        image: postgres:16\n",
    )
    _write(
        tmp_path,
        "frontend/package.json",
        json.dumps(
            {
                "scripts": {
                    "lint:ci": "expo lint --max-warnings=0",
                    "ci": "npm ci",
                }
            }
        ),
    )

    report = audit_repository(tmp_path)
    payload = report.to_payload()
    assert payload["schema_version"] == SCHEMA_VERSION == 1
    assert payload["kind"] == KIND == "build_network_audit"
    assert payload["task_key"] == TASK_ID
    assert payload["conflict_domain"] == CONFLICT_DOMAIN
    assert payload["fail_closed"] is True
    assert "scripts/ignored.py" not in payload["scanned_files"]
    assert "scripts/fetch.sh" in payload["scanned_files"]
    assert "Makefile" in payload["scanned_files"]
    assert ".github/workflows/ci.yml" in payload["scanned_files"]
    assert "frontend/package.json" in payload["scanned_files"]

    by_excerpt = {item.excerpt: item for item in report.findings}
    pip_install = next(item for item in report.findings if "pip install -r requirements.txt" in item.excerpt)
    assert pip_install.classification == CLASSIFICATION_NETWORK_REQUIRED
    assert pip_install.hidden is True
    assert pip_install.source_kind == "makefile"

    wget = next(item for item in report.findings if item.excerpt.startswith("wget"))
    assert wget.classification == CLASSIFICATION_NETWORK_REQUIRED
    assert wget.hidden is True
    assert wget.source_kind == "script"

    pytest_cmd = next(item for item in report.findings if "python -m pytest" in item.excerpt)
    assert pytest_cmd.classification == CLASSIFICATION_OFFLINE
    assert pytest_cmd.source_kind == "pytest"
    assert pytest_cmd.hidden is False

    mystery = next(item for item in report.findings if "custom-linter" in item.excerpt)
    assert mystery.classification == CLASSIFICATION_NETWORK_UNKNOWN
    assert mystery.hidden is True

    unpinned = next(item for item in report.findings if item.excerpt == "uses: actions/checkout@v4")
    assert unpinned.classification == CLASSIFICATION_NETWORK_REQUIRED
    assert unpinned.hidden is True
    assert unpinned.reasons == ("unpinned-action-download",)

    pinned = next(
        item
        for item in report.findings
        if item.excerpt.endswith("actions/setup-python@3d3c42e5aac5ba805825da76410c181273ba90b1")
    )
    assert pinned.hidden is False
    assert pinned.classification == CLASSIFICATION_NETWORK_REQUIRED

    workflow_pip = next(item for item in report.findings if item.excerpt == "python -m pip install pytest")
    assert workflow_pip.source_kind == "workflow"
    assert workflow_pip.classification == CLASSIFICATION_NETWORK_REQUIRED

    compileall = next(
        item
        for item in report.findings
        if item.excerpt == "python -m compileall -q skeleton" and item.path.endswith("ci.yml")
    )
    assert compileall.classification == CLASSIFICATION_OFFLINE

    unknown_tool = next(item for item in report.findings if item.excerpt == "mystery-tool --fast")
    assert unknown_tool.classification == CLASSIFICATION_NETWORK_UNKNOWN

    image = next(item for item in report.findings if item.excerpt.startswith("image: postgres:16"))
    assert image.classification == CLASSIFICATION_NETWORK_REQUIRED
    assert image.hidden is True

    npm_ci = next(item for item in report.findings if item.excerpt.startswith("ci: npm ci"))
    assert npm_ci.classification == CLASSIFICATION_NETWORK_REQUIRED
    assert npm_ci.source_kind == "npm"

    lint = next(item for item in report.findings if "lint:ci" in item.excerpt)
    assert lint.classification == CLASSIFICATION_NETWORK_UNKNOWN
    assert by_excerpt  # payload rows exist
    assert payload["counts"]["network-required"] >= 1
    assert payload["counts"]["network-unknown"] >= 1
    assert payload["counts"]["offline"] >= 1
    assert payload["counts"]["hidden_network_required"] >= 1


def test_offline_classification_never_emitted_without_offline_evidence() -> None:
    report = audit_repository(REPO_ROOT)
    for finding in report.findings:
        if finding.classification == CLASSIFICATION_OFFLINE:
            assert finding.reasons
            assert all(reason.startswith("offline-") for reason in finding.reasons)
            assert finding.hidden is False
        if finding.classification == CLASSIFICATION_NETWORK_UNKNOWN:
            assert not any(reason.startswith("offline-") for reason in finding.reasons)


def test_canonical_repo_flags_known_hidden_network_commands() -> None:
    report = audit_repository(REPO_ROOT)
    payload = report.to_payload()
    assert payload["task_key"] == TASK_ID == "reserve-S026-build-network-audit"
    assert payload["conflict_domain"] == CONFLICT_DOMAIN
    assert payload["fail_closed"] is True

    makefile_pip = [
        item
        for item in report.findings
        if item.path == "Makefile" and "pip install" in item.excerpt
    ]
    assert makefile_pip
    assert all(item.classification == CLASSIFICATION_NETWORK_REQUIRED for item in makefile_pip)
    assert all("pip-install-without-offline" in item.reasons for item in makefile_pip)

    wget = [
        item
        for item in report.findings
        if item.path == "scripts/install_android_toolchain.sh" and item.excerpt.startswith("wget")
    ]
    assert wget
    assert wget[0].classification == CLASSIFICATION_NETWORK_REQUIRED

    workflow_pip = [
        item
        for item in report.findings
        if item.path.startswith(".github/workflows/")
        and "pip install" in item.excerpt
        and item.classification == CLASSIFICATION_NETWORK_REQUIRED
    ]
    assert workflow_pip

    compileall = [
        item
        for item in report.findings
        if item.classification == CLASSIFICATION_OFFLINE and "compileall" in item.excerpt
    ]
    assert compileall


def test_audit_does_not_execute_discovered_commands(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _write(tmp_path, "Makefile", "steal:\n\tcurl https://example.invalid/secret\n")
    _write(tmp_path, "scripts/go.sh", "#!/bin/sh\nwget https://example.invalid/x\n")

    def forbidden(*_args, **_kwargs):
        raise AssertionError("network audit must not execute scanned commands")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(subprocess, "call", forbidden)
    monkeypatch.setattr(subprocess, "check_output", forbidden)

    report = audit_repository(tmp_path)
    assert any(item.classification == CLASSIFICATION_NETWORK_REQUIRED for item in report.findings)


def test_snapshot_and_cli_match(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write(tmp_path, "Makefile", "test:\n\tpython -m compileall -q skeleton\n")
    snapshot = network_audit_snapshot(tmp_path)
    assert snapshot == audit_repository(tmp_path).to_payload()
    assert main(["--root", str(tmp_path)]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed == snapshot


def test_package_does_not_define_incremental_graph() -> None:
    import skeleton.build as package

    assert not hasattr(package, "incremental_graph")
    build_dir = Path(package.__file__).resolve().parent
    assert not (build_dir / "incremental_graph.py").exists()
    assert (build_dir / "network_audit.py").is_file()


def test_comments_are_not_classified_as_commands(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "scripts/notes.sh",
        "#!/bin/sh\n# curl https://example.invalid/never-run\necho ok\n",
    )
    _write(tmp_path, "Makefile", "help:\n\t# wget https://example.invalid/nope\n\techo help\n")
    report = audit_repository(tmp_path)
    excerpts = [item.excerpt for item in report.findings]
    assert not any("curl" in excerpt or "wget" in excerpt for excerpt in excerpts)
    assert any(item.excerpt == "echo ok" and item.classification == CLASSIFICATION_OFFLINE for item in report.findings)
