from __future__ import annotations

from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[2]


def test_legacy_setup_entrypoint_matches_canonical_pyproject() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    canonical = pyproject["project"]["scripts"]["skeleton-dev"]
    setup_cfg = (ROOT / "setup.cfg").read_text(encoding="utf-8")

    assert canonical == "skeleton.developer.cli:main"
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


def test_release_workflow_verifies_native_assembly_wheel_payload() -> None:
    workflow = (
        ROOT / ".github" / "workflows" / "reproducible-release.yml"
    ).read_text(encoding="utf-8")

    assert "Verify native Assembly payload in wheel" in workflow
    assert "exactly one wheel" in workflow
    assert "native Assembly wheel payload missing" in workflow
    assert "native Assembly wheel payload empty" in workflow
    for source in (
        "skeleton_asm.h", "aarch64.S", "x86_64.S", "README.md",
    ):
        assert f"skeleton/native/asm/{source}" in workflow
    assert "skeleton/app/cli.py" in workflow
    assert "skeleton/ai/runtime/game_project_cli.py" in workflow


def test_runtime_image_excludes_development_payload() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert '.[dev]' not in dockerfile
    assert "p['optional-dependencies']['local-inference']" in dockerfile
    assert "p['optional-dependencies']['hosted-inference']" in dockerfile
    assert "pip install --no-cache-dir --no-compile -r /tmp/skeleton-runtime-requirements.txt" in dockerfile
    assert "pip install --no-cache-dir --no-compile --no-deps --no-build-isolation ." in dockerfile
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
    # The glibc runtime uses its reviewed fixed Python 3.14 path.
    assert "/usr/local/lib/python3.14/site-packages/pip" in root_dockerfile
    assert "/usr/local/lib/python3.14/site-packages/pip-*.dist-info" in root_dockerfile
    assert "/usr/local/bin/pip*" in root_dockerfile

    # The Alpine backend uses a guarded sysconfig path because the interpreter
    # owns the live site-packages layout. A hardcoded glibc path would mask a
    # no-op cleanup after Python is updated.
    assert 'site = pathlib.Path(sysconfig.get_path("purelib"))' in production
    assert 'not site.is_relative_to(pathlib.Path("/usr/local/lib"))' in production
    assert 'shutil.rmtree(site / "pip", ignore_errors=True)' in production
    assert 'for dist in site.glob("pip-*.dist-info"):' in production
    assert 'shutil.rmtree(dist)' in production
    assert 'pathlib.Path("/usr/local/bin").glob("pip*")' in production
    assert "pip_bin.unlink()" in production
    assert "unexpected Python site-packages path; refusing runtime pip cleanup" in production

    assert "python -m ensurepip --upgrade" not in production
    assert "python -m ensurepip --upgrade" in development
    assert "python -m pip install --no-cache-dir" in development


def test_runtime_dockerfiles_keep_security_hardening() -> None:
    root_dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    backend_dockerfile = (ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")
    frontend_dockerfile = (ROOT / "frontend" / "Dockerfile").read_text(encoding="utf-8")
    frontend_nginx = (ROOT / "frontend" / "nginx.conf").read_text(encoding="utf-8")

    # Production/build base images must be immutable and runtime users non-root.
    assert "ARG PYTHON_IMAGE=python:3.14-slim@sha256:" in root_dockerfile
    assert "FROM ${PYTHON_IMAGE}" in root_dockerfile
    assert "apt-get install -y --no-install-recommends ca-certificates libgomp1 libstdc++6" in root_dockerfile
    assert "rm -rf /var/lib/apt/lists/*" in root_dockerfile
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
    # Local glibc inference permits only a bounded set of runtime OS packages;
    # the separately pinned Alpine backend retains no apt dependency.
    assert "apt-get install -y --no-install-recommends ca-certificates libgomp1 libstdc++6" in root_dockerfile
    assert "RUN apt-get" not in backend_dockerfile
    assert "curl -f http://localhost:8001/api/health" not in backend_dockerfile


def test_legacy_packaging_metadata_matches_authoritative_project() -> None:
    import configparser

    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    legacy = configparser.ConfigParser()
    legacy.read(ROOT / "setup.cfg", encoding="utf-8")
    for field in ("name", "version", "description"):
        assert legacy["metadata"][field] == project["project"][field]
    assert legacy["options"]["python_requires"] == project["project"]["requires-python"]

    def lines(section, option):
        return {line.strip() for line in legacy[section][option].splitlines() if line.strip()}

    assert lines("options", "install_requires") == set(project["project"]["dependencies"])
    extras = project["project"]["optional-dependencies"]
    assert set(legacy["options.extras_require"]) == set(extras)
    for name, dependencies in extras.items():
        assert lines("options.extras_require", name) == set(dependencies)
    scripts = dict(line.split(" = ", 1) for line in lines("options.entry_points", "console_scripts"))
    assert scripts == project["project"]["scripts"]
    for name, patterns in project["tool"]["setuptools"]["package-data"].items():
        assert lines("options.package_data", name) == set(patterns)
    for name, patterns in project["tool"]["setuptools"]["packages"]["find"].items():
        assert lines("options.packages.find", name) == set(patterns)


def test_installed_game_project_command_is_package_owned(capsys) -> None:
    """The installed app must not rely on checkout-only scripts/ imports."""
    import json
    from scripts.game.game_project import _demo as repository_demo
    from scripts.game.game_project import main as repository_main
    from skeleton.ai.runtime.game_project_cli import _demo as package_demo
    from skeleton.ai.runtime.game_project_cli import main as package_main
    from skeleton.app.cli import run_app_cli

    assert repository_main is package_main
    assert repository_demo is package_demo
    source = (ROOT / "skeleton" / "app" / "cli.py").read_text(encoding="utf-8")
    assert "from skeleton.ai.runtime.game_project_cli import main" in source
    assert "from scripts.game.game_project import main" not in source
    assert run_app_cli(["game-project", "--catalog"]) == 0
    assert isinstance(json.loads(capsys.readouterr().out), dict)
    assert package_main(["--catalog"]) == 0
    assert isinstance(json.loads(capsys.readouterr().out), dict)
