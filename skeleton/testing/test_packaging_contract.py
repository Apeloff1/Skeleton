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


def test_runtime_image_excludes_development_payload() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert '.[dev]' not in dockerfile
    assert "pip install --no-cache-dir ." in dockerfile
    assert "pip install --no-cache-dir -e" not in dockerfile
    assert "COPY tests" not in dockerfile
    assert "USER appuser" in dockerfile


def test_runtime_dockerfiles_keep_security_hardening() -> None:
    root_dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    backend_dockerfile = (ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")

    # Production base images must be immutable and runtime users non-root.
    assert "python:3.14-slim@sha256:" in root_dockerfile
    assert "USER appuser" in root_dockerfile
    assert "/usr/sbin/nologin" in root_dockerfile

    assert "FROM python:3.14-slim@sha256:" in backend_dockerfile
    assert "USER appuser" in backend_dockerfile
    assert "/usr/sbin/nologin" in backend_dockerfile

    # Do not add OS packages just to probe the local service.
    assert "urllib.request.urlopen" in backend_dockerfile
    assert "RUN apt-get" not in backend_dockerfile
    assert "curl -f http://localhost:8001/api/health" not in backend_dockerfile
