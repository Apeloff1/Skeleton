from __future__ import annotations

from pathlib import Path
import subprocess
import json
import re

import pytest

from skeleton.app.installer import InstallPhase, install_application
from skeleton.app.preloader import PreloadCheck, PreloadReport
from skeleton.app.setup_runtime import ensure_runtime_environment


ENV_TEMPLATE = """# test runtime
MONGO_INITDB_ROOT_USERNAME=admin
MONGO_INITDB_ROOT_PASSWORD=
MONGO_URL=
SKL_MONGO_URI=
JWT_SECRET=
OPENAI_API_KEY=sk-your-key-here
"""


def _read_values(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


def test_setup_runtime_creates_complete_secret_backed_environment(tmp_path):
    (tmp_path / ".env.example").write_text(ENV_TEMPLATE, encoding="utf-8")

    result = ensure_runtime_environment(tmp_path)
    values = _read_values(tmp_path / ".env")

    assert result.created is True
    assert result.changed is True
    assert values["MONGO_INITDB_ROOT_PASSWORD"]
    assert len(values["JWT_SECRET"]) == 64
    assert len(values["SKL_ENGINE_SERVICE_TOKEN"]) == 64
    assert values["SKL_ENGINE_SERVICE_TOKEN"] != values["JWT_SECRET"]
    assert values["MONGO_URL"].startswith("mongodb://admin:")
    assert "@mongo:27017/tutolage?authSource=admin" in values["MONGO_URL"]
    assert "@mongo:27017/skeleton?authSource=admin" in values["SKL_MONGO_URI"]
    assert set(result.configured_keys) >= {
        "MONGO_INITDB_ROOT_PASSWORD",
        "MONGO_URL",
        "SKL_MONGO_URI",
        "JWT_SECRET",
        "SKL_ENGINE_SERVICE_TOKEN",
    }


def test_setup_runtime_is_idempotent_and_preserves_existing_secrets(tmp_path):
    (tmp_path / ".env.example").write_text(ENV_TEMPLATE, encoding="utf-8")

    first = ensure_runtime_environment(tmp_path)
    first_text = (tmp_path / ".env").read_text(encoding="utf-8")
    second = ensure_runtime_environment(tmp_path)
    second_text = (tmp_path / ".env").read_text(encoding="utf-8")

    assert first.changed is True
    assert second.created is False
    assert second.changed is False
    assert second_text == first_text
    assert "MONGO_INITDB_ROOT_PASSWORD" in second.preserved_keys
    assert "JWT_SECRET" in second.preserved_keys
    assert "SKL_ENGINE_SERVICE_TOKEN" in second.preserved_keys


def test_setup_runtime_url_encodes_preserved_mongo_credentials(tmp_path):
    (tmp_path / ".env").write_text(
        """MONGO_INITDB_ROOT_USERNAME=local user
MONGO_INITDB_ROOT_PASSWORD=p@ss:word/with space
MONGO_URL=
SKL_MONGO_URI=
JWT_SECRET=unit-test-jwt-secret-not-sensitive
""",
        encoding="utf-8",
    )

    ensure_runtime_environment(tmp_path)
    values = _read_values(tmp_path / ".env")

    assert "local%20user:p%40ss%3Aword%2Fwith%20space" in values["MONGO_URL"]
    assert "local%20user:p%40ss%3Aword%2Fwith%20space" in values["SKL_MONGO_URI"]


def test_setup_receipt_never_contains_secret_values(tmp_path):
    (tmp_path / ".env.example").write_text(ENV_TEMPLATE, encoding="utf-8")

    result = ensure_runtime_environment(tmp_path)
    values = _read_values(tmp_path / ".env")
    serialized = repr(result.to_dict())

    assert values["MONGO_INITDB_ROOT_PASSWORD"] not in serialized
    assert values["JWT_SECRET"] not in serialized
    assert values["MONGO_URL"] not in serialized
    assert values["SKL_MONGO_URI"] not in serialized
    assert values["SKL_ENGINE_SERVICE_TOKEN"] not in serialized


@pytest.mark.parametrize("token", ["", "change-me", "short", "x" * 4097])
def test_setup_repairs_legacy_engine_authentication(tmp_path, token):
    (tmp_path / ".env").write_text(
        ENV_TEMPLATE + f"SKL_ENGINE_SERVICE_TOKEN={token}\n", encoding="utf-8"
    )
    result = ensure_runtime_environment(tmp_path)
    values = _read_values(tmp_path / ".env")
    assert len(values["SKL_ENGINE_SERVICE_TOKEN"]) == 64
    assert "SKL_ENGINE_SERVICE_TOKEN" in result.configured_keys
    assert not ensure_runtime_environment(tmp_path).changed


def test_setup_repairs_duplicate_assignments_and_rotates_engine_token(tmp_path):
    (tmp_path / ".env").write_text(
        ENV_TEMPLATE + "SKL_ENGINE_SERVICE_TOKEN=old\nSKL_ENGINE_SERVICE_TOKEN=\n",
        encoding="utf-8",
    )
    ensure_runtime_environment(tmp_path)
    before = _read_values(tmp_path / ".env")
    result = ensure_runtime_environment(tmp_path, rotate_secrets=True)
    after = _read_values(tmp_path / ".env")
    assignments = [
        line.split("=", 1)[1]
        for line in (tmp_path / ".env").read_text().splitlines()
        if line.startswith("SKL_ENGINE_SERVICE_TOKEN=")
    ]
    assert assignments == [after["SKL_ENGINE_SERVICE_TOKEN"]] * 2
    assert after["SKL_ENGINE_SERVICE_TOKEN"] != before["SKL_ENGINE_SERVICE_TOKEN"]
    assert after["SKL_ENGINE_SERVICE_TOKEN"] not in repr(result.to_dict())
    assert not ensure_runtime_environment(tmp_path).changed


def test_setup_covers_every_required_compose_value(tmp_path):
    """A new Compose requirement cannot silently escape first-run setup."""
    root = Path(__file__).resolve().parents[2]
    (tmp_path / ".env.example").write_text(
        (root / ".env.example").read_text(), encoding="utf-8"
    )
    ensure_runtime_environment(tmp_path)
    values = _read_values(tmp_path / ".env")
    required = set(re.findall(r"\$\{([A-Z_]+):\?", (root / "docker-compose.yml").read_text()))
    manifest = json.loads((root / "skeleton/app/manifest.json").read_text())
    assert required <= set(manifest["runtime"]["required_env"])
    assert all(values.get(key) for key in required)


def test_installer_stops_before_mutation_when_preloader_blocks(tmp_path, monkeypatch):
    report = PreloadReport(
        root=tmp_path,
        platform="test",
        python="3.11",
        checks=(PreloadCheck("host:docker", False, "missing", remediation="install docker"),),
    )
    monkeypatch.setattr("skeleton.app.installer.inspect_host", lambda root, runner, **kwargs: report)

    called = []
    monkeypatch.setattr(
        "skeleton.app.installer.ensure_runtime_environment",
        lambda *args, **kwargs: called.append(True),
    )

    receipt = install_application(tmp_path, install_python=False)

    assert receipt.ok is False
    assert receipt.phases == (
        InstallPhase("preload", False, "host preloader blocked installation: host:docker"),
    )
    assert called == []


def test_installer_skip_python_runs_bounded_validation(tmp_path, monkeypatch):
    (tmp_path / ".env.example").write_text(ENV_TEMPLATE, encoding="utf-8")
    report = PreloadReport(
        root=tmp_path,
        platform="test",
        python="3.11",
        checks=(PreloadCheck("host:ready", True, "ready"),),
    )
    monkeypatch.setattr("skeleton.app.installer.inspect_host", lambda root, runner, **kwargs: report)
    monkeypatch.setattr("skeleton.app.installer.preflight", lambda *args, **kwargs: ())
    monkeypatch.setattr("skeleton.app.installer.checks_ok", lambda checks: True)
    monkeypatch.setattr(
        "skeleton.app.installer.compose_command",
        lambda action, **kwargs: ("docker", "compose", "config"),
    )

    commands = []

    def runner(command, **kwargs):
        commands.append(tuple(command))
        return subprocess.CompletedProcess(command, 0, stdout="valid\n", stderr="")

    receipt = install_application(tmp_path, install_python=False, runner=runner)

    assert receipt.ok is True
    assert [phase.name for phase in receipt.phases] == [
        "preload",
        "setup-runtime",
        "python-install",
        "runtime-preflight",
        "compose-config",
    ]
    assert receipt.phases[2].required is False
    assert commands == [("docker", "compose", "config")]


def test_setup_repairs_stale_local_mongo_uris_after_password_repair(tmp_path):
    (tmp_path / ".env").write_text(
        "MONGO_INITDB_ROOT_USERNAME=admin\n"
        "MONGO_INITDB_ROOT_PASSWORD=change-me\n"
        "MONGO_URL=mongodb://admin:oldpass@mongo:27017/tutolage?authSource=admin\n"
        "SKL_MONGO_URI=mongodb://admin:oldpass@mongo:27017/skeleton?authSource=admin\n"
        "JWT_SECRET=some-valid-preserved-jwt-secret\n",
        encoding="utf-8",
    )
    result = ensure_runtime_environment(tmp_path)
    values = _read_values(tmp_path / ".env")
    new_password = values["MONGO_INITDB_ROOT_PASSWORD"]

    assert result.changed
    assert new_password not in ("", "change-me", "oldpass")
    assert f"mongodb://admin:{new_password}@mongo:27017/" in values["MONGO_URL"]
    assert f"mongodb://admin:{new_password}@mongo:27017/" in values["SKL_MONGO_URI"]
    assert {"MONGO_URL", "SKL_MONGO_URI"} <= set(result.configured_keys)
    assert not ensure_runtime_environment(tmp_path).changed


def test_setup_preserves_external_mongo_when_local_credentials_are_repaired(tmp_path):
    remote_uri = "mongodb://service:remote-password@db.example.net:27017/app"
    (tmp_path / ".env").write_text(
        "MONGO_INITDB_ROOT_USERNAME=admin\n"
        "MONGO_INITDB_ROOT_PASSWORD=change-me\n"
        f"MONGO_URL={remote_uri}\n"
        "SKL_MONGO_URI=mongodb://admin:oldpass@mongo:27017/skeleton?authSource=admin\n"
        "JWT_SECRET=some-valid-preserved-jwt-secret\n",
        encoding="utf-8",
    )
    ensure_runtime_environment(tmp_path)
    values = _read_values(tmp_path / ".env")
    assert values["MONGO_URL"] == remote_uri
    assert values["MONGO_INITDB_ROOT_PASSWORD"] in values["SKL_MONGO_URI"]
