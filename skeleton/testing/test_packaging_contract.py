from __future__ import annotations

from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[2]


def test_legacy_setup_entrypoint_matches_canonical_pyproject() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    canonical = pyproject["project"]["scripts"]["skeleton-dev"]
    setup_cfg = (ROOT / "setup.cfg").read_text(encoding="utf-8")

    assert canonical == "skeleton.developer.cli:run_dev_cli"
    assert f"skeleton-dev = {canonical}" in setup_cfg


def test_native_assembly_sources_and_header_are_package_data() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    package_data = pyproject["tool"]["setuptools"]["package-data"]["skeleton.native"]
    setup_cfg = (ROOT / "setup.cfg").read_text(encoding="utf-8")

    assert "asm/*.S" in package_data
    assert "asm/*.h" in package_data
    assert "asm/*.md" in package_data
    assert "skeleton.native =" in setup_cfg
    assert "asm/*.S" in setup_cfg
    assert "asm/*.h" in setup_cfg


def test_runtime_image_excludes_development_payload() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert '.[dev]' not in dockerfile
    assert "pip install --no-cache-dir ." in dockerfile
    assert "pip install --no-cache-dir -e" not in dockerfile
    assert "COPY tests" not in dockerfile
    assert "USER appuser" in dockerfile


def test_production_images_drop_installer_toolchain() -> None:
    root_dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    backend_dockerfile = (ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")
    production, development = backend_dockerfile.split("FROM production AS development", maxsplit=1)

    # pip 26.2+ carries vendored runtime code and an embedded CycloneDX SBOM.
    # Production images install dependencies first and then remove that entire
    # installer-only surface rather than suppressing scanner findings.
    for dockerfile in (root_dockerfile, production):
        assert "/usr/local/lib/python3.14/site-packages/pip" in dockerfile
        assert "/usr/local/lib/python3.14/site-packages/pip-*.dist-info" in dockerfile
        assert "/usr/local/bin/pip*" in dockerfile

    assert "python -m ensurepip --upgrade" not in production
    assert "python -m ensurepip --upgrade" in development
    assert "python -m pip install --no-cache-dir" in development


def test_runtime_dockerfiles_keep_security_hardening() -> None:
    root_dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    backend_dockerfile = (ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")
    frontend_dockerfile = (ROOT / "frontend" / "Dockerfile").read_text(encoding="utf-8")
    frontend_nginx = (ROOT / "frontend" / "nginx.conf").read_text(encoding="utf-8")

    # Production/build base images must be immutable and runtime users non-root.
    assert "python:3.14-alpine@sha256:" in root_dockerfile
    assert "USER appuser" in root_dockerfile
    assert "/sbin/nologin" in root_dockerfile
    assert "urllib.request.urlopen" in root_dockerfile
    assert "127.0.0.1:8001/api/v1/health/live" in root_dockerfile

    assert "ghcr.io/astral-sh/uv:0.12.4@sha256:" not in backend_dockerfile
    assert "ghcr.io/astral-sh/uv:${UV_VERSION}" not in backend_dockerfile
    assert "python:3.14-alpine@sha256:" in backend_dockerfile
    assert "USER appuser" in backend_dockerfile
    assert "/sbin/nologin" in backend_dockerfile
    assert "ENVIRONMENT=production" in backend_dockerfile
    assert "CORS_ORIGINS=https://cors.invalid" in backend_dockerfile

    assert "FROM nginx:1.31-alpine-slim@sha256:" in frontend_dockerfile
    assert "USER nginx" in frontend_dockerfile
    assert "EXPOSE 8080" in frontend_dockerfile
    assert "127.0.0.1:8080/healthz" in frontend_dockerfile
    assert "listen 8080;" in frontend_nginx
    assert "listen 80;" not in frontend_nginx

    # Do not add OS packages just to probe the local service.
    assert "urllib.request.urlopen" in backend_dockerfile
    assert "RUN apt-get" not in root_dockerfile
    assert "RUN apt-get" not in backend_dockerfile
    assert "curl -f http://localhost:8001/api/health" not in backend_dockerfile
