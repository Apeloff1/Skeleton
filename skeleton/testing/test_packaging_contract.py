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
