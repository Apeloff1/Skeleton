"""Contract for the frontend Jest CI workflow."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WF = ROOT / ".github" / "workflows" / "frontend-jest.yml"
PKG = ROOT / "frontend" / "package.json"


def _text() -> str:
    return WF.read_text(encoding="utf-8")


def test_concurrency_matches_4251_rule():
    t = _text()
    assert "group: frontend-jest-${{ github.event_name }}-${{ github.event.pull_request.number || github.sha }}" in t
    assert "cancel-in-progress: ${{ github.event_name == 'pull_request' }}" in t


def test_least_privilege_and_frozen_install():
    t = _text()
    assert "permissions:\n  contents: read" in t
    assert "persist-credentials: false" in t
    assert "yarn install --frozen-lockfile --ignore-scripts" in t


def test_runs_jest_script_declared_in_package_json():
    pkg = json.loads(PKG.read_text(encoding="utf-8"))
    assert "jest" in pkg["scripts"]["test:jest"]
    assert "jest" in pkg["devDependencies"] and "jest-expo" in pkg["devDependencies"]
    assert "run: yarn test:jest" in _text()


def test_jest_config_targets_tests_dir():
    cfg = (ROOT / "frontend" / "jest.config.js").read_text(encoding="utf-8")
    assert "jest-expo" in cfg and "__tests__" in cfg
