"""Release pipeline contract: single VERSION source, changelog generation, image workflow."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


drift = _load("check_version_drift")
changelog = _load("generate_changelog")


def test_all_manifests_match_version_file():
    assert drift.check() == []
    assert drift.read_version() == "16.0.0"


def test_tag_must_match_version():
    v = drift.read_version()
    assert drift.check(f"v{v}") == []
    assert drift.check(f"refs/tags/v{v}") == []
    assert any("does not match" in p for p in drift.check("v0.0.1"))


def test_drift_detected(monkeypatch, tmp_path):
    (tmp_path / "VERSION").write_text("1.2.3\n")
    monkeypatch.setattr(drift, "ROOT", tmp_path)
    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend" / "package.json").write_text('{"version": "1.2.4"}')
    problems = drift.check()
    assert any("frontend/package.json" in p and "1.2.4" in p for p in problems)
    assert any("pyproject.toml: cannot read" in p for p in problems)


def test_semver_validation():
    assert drift.SEMVER.match("16.0.0") and drift.SEMVER.match("1.0.0-rc.1+build.5")
    assert not drift.SEMVER.match("v16.0.0") and not drift.SEMVER.match("16.0")


def test_changelog_groups_conventional_commits():
    out = changelog.render("2.0.0", [
        "feat(api): add widgets", "fix: crash on boot", "feat!: drop v1 routes",
        "ci: speed up", "Merge pull request #1 from x", "random subject", "fix: crash on boot",
    ], when=date(2026, 10, 17))
    assert out.startswith("## v2.0.0 (2026-10-17)")
    assert "### Breaking changes\n- drop v1 routes" in out
    assert "### Features\n- **api:** add widgets" in out
    assert out.count("crash on boot") == 1
    assert "Merge pull request" not in out
    assert "### Other changes\n- random subject" in out


def test_changelog_empty():
    assert "_No changes._" in changelog.render("1.0.0", [], when=date(2026, 1, 1))


def test_changelog_cli_runs_against_repo_history():
    head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True)
    if head.returncode != 0:
        return
    res = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "generate_changelog.py"), "--version", "9.9.9",
         "--from", "HEAD~1", "--to", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    if "HEAD~1" in res.stderr:  # shallow clone with a single commit
        return
    assert res.returncode == 0, res.stderr
    assert res.stdout.startswith("## v9.9.9 (")


def test_release_images_workflow_is_least_privilege_and_tag_triggered():
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "release-images.yml").read_text())
    on = wf.get("on", wf.get(True))
    assert on["push"]["tags"] == ["v*"]
    assert wf["permissions"] == {"contents": "read"}
    job = wf["jobs"]["publish"]
    assert job["permissions"] == {"contents": "read", "packages": "write"}
    text = (ROOT / ".github" / "workflows" / "release-images.yml").read_text()
    assert "secrets.GITHUB_TOKEN" in text
    assert "secrets." not in text.replace("secrets.GITHUB_TOKEN", "")
    assert "check_version_drift.py --tag" in text
    assert "APP_VERSION=" in text and "ghcr.io/" in text
    for step in job["steps"]:
        uses = step.get("uses")
        if uses:
            assert "@" in uses and len(uses.split("@")[1].split()[0]) == 40, uses


def test_dockerfiles_bake_app_version():
    backend = (ROOT / "backend" / "Dockerfile").read_text()
    assert "ARG APP_VERSION=dev" in backend and "ENV APP_VERSION=$APP_VERSION" in backend
    assert "org.opencontainers.image.version=$APP_VERSION" in (ROOT / "frontend" / "Dockerfile").read_text()
