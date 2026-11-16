"""Adversarial, source-only pre-first-install Docker context qualification.

No Docker daemon, secret mutation, network call, or image build is required.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from skeleton.app.assembly import find_repo_root, preflight
from skeleton.app.install_source_contracts import (
    _copy_sources,
    _source_path_error,
    build_source_errors,
    nginx_ingress_errors,
)


def _fixture(root: Path) -> None:
    (root / "backend").mkdir()
    (root / "frontend").mkdir()
    (root / "frontend" / "scripts").mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='fixture'\n", encoding="utf-8")
    (root / "backend" / "requirements.txt").write_text("httpx\n", encoding="utf-8")
    (root / "frontend" / "package.json").write_text("{}", encoding="utf-8")
    (root / "frontend" / "yarn.lock").write_text("# lock\n", encoding="utf-8")
    (root / "frontend" / "index.js").write_text("export {};\n", encoding="utf-8")
    (root / "frontend" / "scripts" / "asset.js").write_text("export {};\n", encoding="utf-8")

    (root / "Dockerfile").write_text(
        "FROM python:3.14-slim\n"
        "COPY pyproject.toml ./\n"
        "COPY --chown=appuser:appuser . .\n",
        encoding="utf-8",
    )
    (root / "backend" / "Dockerfile").write_text(
        "FROM python:3.14-alpine AS builder\n"
        "COPY backend/requirements.txt ./\n"
        "FROM builder AS production\n"
        "COPY --from=builder /opt/venv /opt/venv\n",
        encoding="utf-8",
    )
    (root / "frontend" / "Dockerfile").write_text(
        "FROM node:24-alpine AS deps\n"
        "COPY package.json yarn.lock* ./\n"
        "COPY index.js ./index.js\n"
        "COPY scripts/asset.js ./scripts/\n",
        encoding="utf-8",
    )
    private_names = (
        ".env", ".env.*", "..env.*", "*.pem", "*.key", "*.p12", "*.pfx", "*.crt", "*.cer",
        "credentials*.json", "service-account*.json", ".runtime",
    )
    private_globs = "".join(f"**/{name}\n" for name in private_names)
    (root / "Dockerfile.dockerignore").write_text(private_globs, encoding="utf-8")
    (root / "backend" / "Dockerfile.dockerignore").write_text(
        private_globs, encoding="utf-8"
    )
    (root / "frontend" / ".dockerignore").write_text(
        "".join(f"{name}\n" for name in private_names) + private_globs,
        encoding="utf-8"
    )


def test_current_repository_build_sources_are_complete_and_bounded():
    root = find_repo_root(Path(__file__))
    assert build_source_errors(root) == ()
    check = next(c for c in preflight(root) if c.code == "image:build-inputs")
    assert check.ok, check.message


def test_build_source_fixture_accepts_all_three_contexts(tmp_path):
    _fixture(tmp_path)
    assert build_source_errors(tmp_path) == ()


@pytest.mark.parametrize(
    "missing",
    [
        "pyproject.toml",
        "backend/requirements.txt",
        "frontend/package.json",
        "frontend/yarn.lock",
        "frontend/index.js",
        "frontend/scripts/asset.js",
    ],
)
def test_missing_docker_copy_input_fails_preinstall(tmp_path, missing):
    _fixture(tmp_path)
    (tmp_path / missing).unlink()
    errors = build_source_errors(tmp_path)
    assert any("required Docker COPY input missing" in item for item in errors)


def test_docker_from_stage_copies_do_not_require_host_files(tmp_path):
    _fixture(tmp_path)
    assert not any("opt/venv" in item for item in build_source_errors(tmp_path))
    assert _copy_sources("COPY --from=builder /opt/venv /opt/venv") == ()


def test_docker_source_path_rejects_parent_escape_and_absolute_paths(tmp_path):
    for source in ("../secret", "backend/../secrets", "/etc/passwd", "C:/secret", r"..\secret"):
        assert _source_path_error(tmp_path, source) is not None


def test_docker_context_rejects_host_symlink_input(tmp_path):
    _fixture(tmp_path)
    source = tmp_path / "frontend" / "index.js"
    source.unlink()
    external = tmp_path / "external"
    external.write_text("do-not-copy", encoding="utf-8")
    try:
        source.symlink_to(external)
    except (OSError, NotImplementedError):
        pytest.skip("host symlink creation unsupported")
    assert any("linked or unsafe" in item for item in build_source_errors(tmp_path))


def test_docker_context_rejects_symlink_build_context(tmp_path):
    _fixture(tmp_path)
    backend_dir = tmp_path / "backend"
    # A malicious symlink may be inserted into any named COPY source. Reject
    # it before Docker includes filesystem content outside the declared tree.
    requirements = backend_dir / "requirements.txt"
    requirements.unlink()
    secret = tmp_path / "secret"
    secret.write_text("do-not-copy", encoding="utf-8")
    try:
        requirements.symlink_to(secret)
    except (OSError, NotImplementedError):
        pytest.skip("host symlink creation unsupported")
    assert any("linked or unsafe" in item for item in build_source_errors(tmp_path))


@pytest.mark.parametrize("ignore", [
    "Dockerfile.dockerignore",
    "backend/Dockerfile.dockerignore",
    "frontend/.dockerignore",
])
def test_docker_context_refuses_missing_secret_exclusion_rules(tmp_path, ignore):
    _fixture(tmp_path)
    (tmp_path / ignore).write_text("node_modules\n", encoding="utf-8")
    assert any("private runtime files" in item for item in build_source_errors(tmp_path))


def test_docker_context_refuses_unreviewed_copy_flags(tmp_path):
    _fixture(tmp_path)
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text(
        dockerfile.read_text(encoding="utf-8") + "COPY --unknown=unsafe pyproject.toml ./\n",
        encoding="utf-8",
    )
    assert any("invalid Docker COPY syntax" in item for item in build_source_errors(tmp_path))


def test_docker_context_refuses_copy_parent_traversal(tmp_path):
    _fixture(tmp_path)
    dockerfile = tmp_path / "frontend" / "Dockerfile"
    dockerfile.write_text(
        dockerfile.read_text(encoding="utf-8") + "COPY ../operator-secret ./\n",
        encoding="utf-8",
    )
    assert any("COPY source escapes" in item for item in build_source_errors(tmp_path))


def test_docker_context_refuses_unbounded_copy_glob(tmp_path, monkeypatch):
    from skeleton.app import install_source_contracts

    _fixture(tmp_path)
    (tmp_path / "frontend" / "yarn.lock.extra").write_text(
        "# another lock\n", encoding="utf-8"
    )
    monkeypatch.setattr(install_source_contracts, "MAX_MATCHES_PER_SOURCE", 1)
    assert any("exceeds match limit" in item for item in build_source_errors(tmp_path))


def test_docker_context_rejects_oversize_source_manifest(tmp_path):
    _fixture(tmp_path)
    (tmp_path / "frontend" / "Dockerfile").write_bytes(b"F" * (128 * 1024 + 1))
    assert any("oversized" in item for item in build_source_errors(tmp_path))


def test_docker_context_rejects_invalid_source_encoding(tmp_path):
    _fixture(tmp_path)
    (tmp_path / "backend" / "Dockerfile").write_bytes(b"\xff")
    assert any("unreadable" in item for item in build_source_errors(tmp_path))


def test_docker_context_rejects_dangling_copy_glob(tmp_path):
    _fixture(tmp_path)
    dockerfile = tmp_path / "frontend" / "Dockerfile"
    text = dockerfile.read_text(encoding="utf-8")
    dockerfile.write_text(
        text.replace("COPY package.json yarn.lock* ./", "COPY package.json no-such-lock* ./"),
        encoding="utf-8",
    )
    assert any("no-such-lock*" in item for item in build_source_errors(tmp_path))


def test_docker_context_reports_bounded_errors(tmp_path):
    _fixture(tmp_path)
    dockerfile = tmp_path / "frontend" / "Dockerfile"
    dockerfile.write_text(
        dockerfile.read_text(encoding="utf-8")
        + "".join(f"COPY missing-{i}.txt ./\n" for i in range(80)),
        encoding="utf-8",
    )
    errors = build_source_errors(tmp_path)
    assert len(errors) <= 33
    assert "further build input defects suppressed" in errors



def test_smoke_cli_refuses_unsafe_env_without_network(monkeypatch, tmp_path, capsys):
    import json

    from skeleton.app import cli

    (tmp_path / ".env").write_bytes(b"A" * (256 * 1024 + 1))
    monkeypatch.setattr(cli, "find_repo_root", lambda: tmp_path)

    def forbidden(*_args, **_kwargs):
        pytest.fail("unsafe .env must not cause a network health probe")

    monkeypatch.setattr("skeleton.app.health.wait_for_application", forbidden)
    assert cli.run_app_cli(["smoke", "--json"]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["code"] == "runtime_configuration_unavailable"
    assert payload["results"] == []
    assert "AAAA" not in repr(payload)


def test_status_cli_returns_redacted_error_for_invalid_config(monkeypatch, tmp_path, capsys):
    import json

    from skeleton.app import cli
    from skeleton.app.assembly import runtime_manifest

    (tmp_path / ".env").write_bytes(b"B" * (256 * 1024 + 1))
    monkeypatch.setattr(
        cli, "runtime_manifest",
        lambda *_args, **_kwargs: runtime_manifest(root=tmp_path, environ={}),
    )
    assert cli.run_app_cli(["status", "--json"]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["ok"] is False
    assert report["code"] == "runtime_configuration_unavailable"
    assert "BBBB" not in repr(report)


# The deployed frontend previously exited before healthz because seven exact
# /setup blocks survived repeated source-preserving integration.
_INGRESS = r'''
server {
    # location = /setup { ignored comment
    location = /setup {
        try_files /setup.html /setup/index.html =404;
        add_header Cache-Control "no-store" always;
        add_header Permissions-Policy "camera=(), microphone=(), geolocation=()" always;
        add_header Content-Security-Policy "frame-ancestors 'self'; base-uri 'self'; object-src 'none'" always;
    }
    location = /healthz { return 200 "ok\n"; }
    location / { try_files $uri /index.html; }
}
'''


def _production_fixture(root):
    _fixture(root)
    dockerfile = root / "frontend" / "Dockerfile"
    dockerfile.write_text(dockerfile.read_text(encoding="utf-8")
                          + "FROM nginx:1.31-alpine AS production\n"
                          + "COPY nginx.conf /etc/nginx/conf.d/default.conf\n",
                          encoding="utf-8")
    (root / "frontend" / "nginx.conf").write_text(_INGRESS, encoding="utf-8")


def test_production_ingress_accepts_reviewed_exact_setup_and_literal_health(tmp_path):
    _production_fixture(tmp_path)
    assert build_source_errors(tmp_path) == ()
    assert nginx_ingress_errors(_INGRESS) == ()


@pytest.mark.parametrize("duplicate", [
    'location = /setup { return 200 "not setup"; }',
    'location\n  =\n  "/setup"\n  { return 200 "not setup"; }',
    'location = /healthz { return 200 "not healthy"; }',
    'location ^~ / { return 200 "duplicate prefix"; }',
])
def test_production_ingress_rejects_duplicate_location_before_install(tmp_path, duplicate):
    _production_fixture(tmp_path)
    path = tmp_path / "frontend" / "nginx.conf"
    path.write_text(_INGRESS.rsplit("}", 1)[0] + duplicate + "\n}", encoding="utf-8")
    assert any("duplicate production ingress location" in issue
               for issue in build_source_errors(tmp_path))


@pytest.mark.parametrize("source,reason", [
    (_INGRESS.replace("=404", "/index.html"), "exported route or return 404"),
    (_INGRESS.replace("camera=()", "camera=(self)"), "privacy or cache policy drift"),
    (_INGRESS.replace('add_header Cache-Control "no-store" always;',
                      'add_header Cache-Control "no-store";'), "privacy or cache policy drift"),
    (_INGRESS.replace('add_header Cache-Control "no-store" always;',
                      'add_header Cache-Control "no-store" always;\n        add_header Cache-Control "public" always;'),
     "privacy or cache policy drift"),
    (_INGRESS.replace('add_header Cache-Control "no-store" always;', ""),
     "privacy or cache policy drift"),
    (_INGRESS.replace("location = /setup", "location /setup"), "missing exact setup"),
    (_INGRESS.replace('return 200 "ok\\n";', 'return 200 "wrong";'), "literal liveness"),
    (_INGRESS.replace("server {", "server {\ninclude alternate.conf;"), "unreviewed include"),
    (_INGRESS.replace("\n    location = /setup {", "\n    location = /setup {\n        if ($uri) { return 200; }"),
     "nested block"),
    (_INGRESS + "}", "malformed"),
    (_INGRESS + "'unterminated", "malformed"),
])
def test_ingress_policy_refuses_unreviewed_mutations(source, reason):
    assert any(reason in issue for issue in nginx_ingress_errors(source))


def test_production_ingress_rejects_missing_config(tmp_path):
    _production_fixture(tmp_path)
    (tmp_path / "frontend" / "nginx.conf").unlink()
    assert any("production ingress missing" in issue for issue in build_source_errors(tmp_path))


def test_production_ingress_rejects_oversized_config(tmp_path):
    _production_fixture(tmp_path)
    (tmp_path / "frontend" / "nginx.conf").write_bytes(b"x" * (128 * 1024 + 1))
    assert any("production ingress missing" in issue for issue in build_source_errors(tmp_path))


def test_repository_ingress_preserves_one_exact_setup_location():
    root = find_repo_root(Path(__file__))
    source = (root / "frontend" / "nginx.conf").read_text(encoding="utf-8")
    assert nginx_ingress_errors(source) == ()


@pytest.mark.parametrize("ignore", [
    "Dockerfile.dockerignore",
    "backend/Dockerfile.dockerignore",
    "frontend/.dockerignore",
])
@pytest.mark.parametrize("exception", ["!**", "!skeleton/**", "!**/.env", "!**/.runtime/"])
def test_context_privacy_fence_refuses_late_reinclusion(tmp_path, ignore, exception):
    _fixture(tmp_path)
    path = tmp_path / ignore
    path.write_text(path.read_text() + exception + "\n")
    assert any("private runtime files" in item for item in build_source_errors(tmp_path))


def test_context_privacy_fence_accepts_reinclusion_before_complete_fence(tmp_path):
    _fixture(tmp_path)
    path = tmp_path / "Dockerfile.dockerignore"
    path.write_text("**\n!skeleton/**\n" + path.read_text())
    assert build_source_errors(tmp_path) == ()


@pytest.mark.parametrize("rule", ["**/.env", "**/*.pfx", "**/credentials*.json", "**/.runtime"])
def test_frontend_nested_private_material_must_be_excluded(tmp_path, rule):
    _fixture(tmp_path)
    path = tmp_path / "frontend" / ".dockerignore"
    path.write_text(path.read_text().replace(rule + "\n", ""))
    assert any("private runtime files" in item for item in build_source_errors(tmp_path))


def test_frontend_dockerfile_specific_ignore_cannot_shadow_reviewed_policy(tmp_path):
    _fixture(tmp_path)
    (tmp_path / "frontend" / "Dockerfile.dockerignore").write_text("node_modules\n")
    assert any("unsafe Docker context ignore" in item for item in build_source_errors(tmp_path))


@pytest.mark.parametrize("line", [
    "COPY --from=builder --unknown=x /opt/venv /opt/venv",
    "COPY --from=builder",
    "COPY --from= /opt/venv /opt/venv",
    "COPY --from=builder --from=other /opt/venv /opt/venv",
    "COPY --link-malformed pyproject.toml ./",
    "COPY --link=maybe pyproject.toml ./",
    r"COPY ..\secret ./",
    "COPY '' ./",
])
def test_stage_and_host_copy_parser_rejects_ambiguous_instructions(line):
    assert _copy_sources(line) is None


@pytest.mark.parametrize("instruction", [
    "ADD https://example.invalid/archive.tar.gz /app/",
    "ADD pyproject.toml ./",
])
def test_unreviewed_add_cannot_bypass_source_admission(tmp_path, instruction):
    _fixture(tmp_path)
    path = tmp_path / "Dockerfile"
    path.write_text(path.read_text() + instruction + "\n")
    assert any("unreviewed Docker ADD" in item for item in build_source_errors(tmp_path))


def test_ingress_refuses_nul_even_inside_comment_or_quoted_string():
    for source in (_INGRESS + "# hidden\x00\n", _INGRESS.replace("no-store", "no-store\x00")):
        assert nginx_ingress_errors(source)



@pytest.mark.parametrize("ignore", [
    "Dockerfile.dockerignore", "backend/Dockerfile.dockerignore", "frontend/.dockerignore",
])
def test_legacy_double_dot_secret_staging_must_remain_excluded(tmp_path, ignore):
    _fixture(tmp_path)
    path = tmp_path / ignore
    path.write_text(path.read_text().replace("**/..env.*\n", ""))
    assert any("private runtime files" in error for error in build_source_errors(tmp_path))
