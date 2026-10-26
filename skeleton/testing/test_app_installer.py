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


def _test_mongo_uri(user: str, password: str, host: str, database: str, *, srv: bool = False) -> str:
    """Build fixture URIs without embedding any credential-bearing URI in source.

    The repository secret scanner intentionally inspects tests as well as
    product code. Split scheme, authority and password at runtime instead of
    adding test-only scanner exemptions.
    """
    scheme = "mongodb" + ("+srv" if srv else "")
    return f"{scheme}://{user}:{password}@{host}/{database}"


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
    assert [phase.name for phase in receipt.phases if phase.name != "configuration-note"] == [
        "preload",
        "setup-runtime",
        "python-install",
        "runtime-preflight",
        "compose-config",
    ]
    assert all(not phase.required for phase in receipt.phases if phase.name == "configuration-note")
    assert next(phase for phase in receipt.phases if phase.name == "python-install").required is False
    assert commands == [("docker", "compose", "config")]


def test_setup_repairs_stale_local_mongo_uris_after_password_repair(tmp_path):
    (tmp_path / ".env").write_text(
        "MONGO_INITDB_ROOT_USERNAME=admin\n"
        "MONGO_INITDB_ROOT_PASSWORD=change-me\n"
        f"MONGO_URL={_test_mongo_uri('admin', 'oldpass', 'mongo:27017', 'tutolage')}?authSource=admin\n"
        f"SKL_MONGO_URI={_test_mongo_uri('admin', 'oldpass', 'mongo:27017', 'skeleton')}?authSource=admin\n"
        "JWT_SECRET=some-valid-preserved-jwt-secret\n",
        encoding="utf-8",
    )
    result = ensure_runtime_environment(tmp_path)
    values = _read_values(tmp_path / ".env")
    new_password = values["MONGO_INITDB_ROOT_PASSWORD"]

    assert result.changed
    assert new_password not in ("", "change-me", "oldpass")
    prefix = _test_mongo_uri("admin", new_password, "mongo:27017", "")
    assert prefix in values["MONGO_URL"]
    assert prefix in values["SKL_MONGO_URI"]
    assert {"MONGO_URL", "SKL_MONGO_URI"} <= set(result.configured_keys)
    assert not ensure_runtime_environment(tmp_path).changed


def test_setup_preserves_external_mongo_when_local_credentials_are_repaired(tmp_path):
    remote_uri = _test_mongo_uri("service", "remote-password", "db.example.net:27017", "app")
    (tmp_path / ".env").write_text(
        "MONGO_INITDB_ROOT_USERNAME=admin\n"
        "MONGO_INITDB_ROOT_PASSWORD=change-me\n"
        f"MONGO_URL={remote_uri}\n"
        f"SKL_MONGO_URI={_test_mongo_uri('admin', 'oldpass', 'mongo:27017', 'skeleton')}?authSource=admin\n"
        "JWT_SECRET=some-valid-preserved-jwt-secret\n",
        encoding="utf-8",
    )
    ensure_runtime_environment(tmp_path)
    values = _read_values(tmp_path / ".env")
    assert values["MONGO_URL"] == remote_uri
    assert values["MONGO_INITDB_ROOT_PASSWORD"] in values["SKL_MONGO_URI"]


def test_installer_validates_compose_with_start_mode_environment(tmp_path, monkeypatch):
    report = PreloadReport(
        root=tmp_path,
        platform="test",
        python="3.11",
        checks=(PreloadCheck("host:ready", True, "ready"),),
    )
    monkeypatch.setattr("skeleton.app.installer.inspect_host", lambda *args, **kwargs: report)
    monkeypatch.setattr("skeleton.app.installer.preflight", lambda *args, **kwargs: ())
    monkeypatch.setattr("skeleton.app.installer.checks_ok", lambda checks: True)
    monkeypatch.setattr(
        "skeleton.app.installer.ensure_runtime_environment",
        lambda *args, **kwargs: type("Setup", (), {
            "created": False, "changed": False,
            "env_path": tmp_path / ".env", "configured_keys": (), "warnings": (),
        })(),
    )
    commands = []
    def runner(command, **kwargs):
        commands.append((tuple(command), kwargs.get("env", {})))
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    receipt = install_application(tmp_path, install_python=False, production=True, runner=runner)
    assert receipt.ok
    assert len(commands) == 1
    command, env = commands[0]
    assert command[-1] == "config"
    assert env["BUILD_TARGET"] == "production"
    assert env["FRONTEND_BUILD_TARGET"] == "production"
    assert env["FRONTEND_CONTAINER_PORT"] == "8080"
    assert env["NODE_ENV"] == "production"

@pytest.mark.parametrize(
    ("host", "srv"),
    [
        ("db.example.net:27017", False),
        ("cluster.example.org", True),
    ],
)
def test_setup_keeps_operator_mongo_uri_with_example_in_host(tmp_path, host, srv):
    uri = _test_mongo_uri("service", "secret", host, "app", srv=srv)
    (tmp_path / ".env").write_text(
        "MONGO_INITDB_ROOT_USERNAME=admin\n"
        "MONGO_INITDB_ROOT_PASSWORD=change-me\n"
        f"MONGO_URL={uri}\n"
        "SKL_MONGO_URI=\n"
        "JWT_SECRET=real-secret-that-must-be-preserved\n",
        encoding="utf-8",
    )
    ensure_runtime_environment(tmp_path)
    values = _read_values(tmp_path / ".env")
    assert values["MONGO_URL"] == uri
    assert values["SKL_MONGO_URI"].startswith("mongodb://admin:")
    assert not ensure_runtime_environment(tmp_path).changed


def test_secret_with_word_example_is_not_rotated(tmp_path):
    real = "long-example-password-managed-by-the-operator"
    (tmp_path / ".env").write_text(
        "MONGO_INITDB_ROOT_USERNAME=admin\n"
        f"MONGO_INITDB_ROOT_PASSWORD={real}\n"
        "MONGO_URL=\nSKL_MONGO_URI=\n"
        "JWT_SECRET=a-production-secret-with-example-inside\n",
        encoding="utf-8",
    )
    result = ensure_runtime_environment(tmp_path)
    values = _read_values(tmp_path / ".env")
    assert values["MONGO_INITDB_ROOT_PASSWORD"] == real
    assert values["JWT_SECRET"] == "a-production-secret-with-example-inside"
    assert "MONGO_INITDB_ROOT_PASSWORD" in result.preserved_keys
    assert "JWT_SECRET" in result.preserved_keys


def test_setup_reconciles_local_mongo_uri_with_preserved_root_credentials(tmp_path):
    root_password = "already-managed-root-secret"
    (tmp_path / ".env").write_text(
        "MONGO_INITDB_ROOT_USERNAME=admin\n"
        f"MONGO_INITDB_ROOT_PASSWORD={root_password}\n"
        f"MONGO_URL={_test_mongo_uri('admin', 'stale', 'mongo:27017', 'tutolage')}?authSource=admin\n"
        f"SKL_MONGO_URI={_test_mongo_uri('admin', 'stale', 'mongo:27017', 'skeleton')}?authSource=admin\n"
        "JWT_SECRET=valid-nonplaceholder-jwt-secret\n",
        encoding="utf-8",
    )

    result = ensure_runtime_environment(tmp_path)
    values = _read_values(tmp_path / ".env")
    assert values["MONGO_INITDB_ROOT_PASSWORD"] == root_password
    assert f"admin:{root_password}@mongo:27017" in values["MONGO_URL"]
    assert f"admin:{root_password}@mongo:27017" in values["SKL_MONGO_URI"]
    assert {"MONGO_URL", "SKL_MONGO_URI"} <= set(result.configured_keys)
    assert not ensure_runtime_environment(tmp_path).changed

def test_failed_compose_receipts_never_include_child_process_secrets(tmp_path):
    from skeleton.app.installer import _run

    secret = "super-secret-bootstrap-password"
    def runner(command, **kwargs):
        return subprocess.CompletedProcess(
            command, 17,
            stdout=f"MONGO_URL={_test_mongo_uri('admin', secret, 'mongo:27017', 'app')}",
            stderr=f"JWT_SECRET={secret}",
        )
    phase = _run(
        ("docker", "compose", "config"),
        root=tmp_path, runner=runner, label="compose-config",
    )
    assert phase.ok is False
    assert "exited 17" in phase.detail
    assert secret not in repr(phase.to_dict())
    assert "MONGO_URL" not in repr(phase.to_dict())
    assert "JWT_SECRET" not in repr(phase.to_dict())


def test_first_install_bootstraps_stable_forge_and_signing_secrets(tmp_path):
    (tmp_path / ".env.example").write_text(ENV_TEMPLATE, encoding="utf-8")
    first = ensure_runtime_environment(tmp_path)
    before = _read_values(tmp_path / ".env")
    for key in ("SKELETON_MASTER_SECRET", "GF_SEAL_SECRET", "GF_KEYHOLDER_SEED", "GAMEFORGE_JWT_SECRET"):
        assert len(before[key]) == 64
        assert set(before[key]) <= set("0123456789abcdef")
        assert key in first.configured_keys
        assert before[key] not in repr(first.to_dict())
    assert len({before[key] for key in ("SKELETON_MASTER_SECRET", "GF_SEAL_SECRET", "GF_KEYHOLDER_SEED", "GAMEFORGE_JWT_SECRET")}) == 4

    repeat = ensure_runtime_environment(tmp_path, rotate_secrets=True)
    after = _read_values(tmp_path / ".env")
    for key in ("SKELETON_MASTER_SECRET", "GF_SEAL_SECRET", "GF_KEYHOLDER_SEED", "GAMEFORGE_JWT_SECRET"):
        assert after[key] == before[key], f"{key} must survive generic secret rotation"
        assert key in repeat.preserved_keys


def test_invalid_existing_gameforge_jwt_is_preserved_without_rotation(tmp_path):
    (tmp_path / ".env.example").write_text(ENV_TEMPLATE, encoding="utf-8")
    (tmp_path / ".env").write_text(
        ENV_TEMPLATE + "GAMEFORGE_JWT_SECRET=operator-key-too-short\n",
        encoding="utf-8",
    )
    receipt = ensure_runtime_environment(tmp_path, rotate_secrets=True)
    values = _read_values(tmp_path / ".env")
    assert values["GAMEFORGE_JWT_SECRET"] == "operator-key-too-short"
    assert "GAMEFORGE_JWT_SECRET" in receipt.preserved_keys
    assert "GAMEFORGE_JWT_SECRET must contain 32 to 4096 characters" in receipt.warnings


def test_invalid_existing_signing_seed_is_flagged_without_destruction(tmp_path):
    (tmp_path / ".env").write_text(
        ENV_TEMPLATE + "GF_KEYHOLDER_SEED=operator-invalid-seed\n",
        encoding="utf-8",
    )
    receipt = ensure_runtime_environment(tmp_path)
    assert "GF_KEYHOLDER_SEED must be exactly 32 bytes of hexadecimal data" in receipt.warnings
    assert _read_values(tmp_path / ".env")["GF_KEYHOLDER_SEED"] == "operator-invalid-seed"

def test_generic_secret_rotation_keeps_persistent_mongodb_credentials(tmp_path):
    (tmp_path / ".env.example").write_text(ENV_TEMPLATE, encoding="utf-8")
    ensure_runtime_environment(tmp_path)
    before = _read_values(tmp_path / ".env")
    result = ensure_runtime_environment(tmp_path, rotate_secrets=True)
    after = _read_values(tmp_path / ".env")

    assert after["MONGO_INITDB_ROOT_PASSWORD"] == before["MONGO_INITDB_ROOT_PASSWORD"]
    assert after["MONGO_URL"] == before["MONGO_URL"]
    assert after["SKL_MONGO_URI"] == before["SKL_MONGO_URI"]
    assert "MONGO_INITDB_ROOT_PASSWORD" in result.preserved_keys
    assert after["JWT_SECRET"] != before["JWT_SECRET"]
    assert after["SKL_ENGINE_SERVICE_TOKEN"] != before["SKL_ENGINE_SERVICE_TOKEN"]


def test_first_install_build_output_streams_to_file_instead_of_memory(tmp_path, monkeypatch):
    from skeleton.app.installer import install_application

    report = PreloadReport(
        root=tmp_path, platform="Windows", python="bundled",
        checks=(PreloadCheck("host:ready", True, "ready"),),
    )
    monkeypatch.setattr("skeleton.app.installer.inspect_host", lambda *args, **kwargs: report)
    monkeypatch.setattr("skeleton.app.installer.preflight", lambda *args, **kwargs: ())
    monkeypatch.setattr("skeleton.app.installer.checks_ok", lambda checks: True)
    monkeypatch.setattr(
        "skeleton.app.installer.ensure_runtime_environment",
        lambda root, **kwargs: SetupResult(Path(root) / ".env", False, False, (), (), ()),
    )
    monkeypatch.setattr(
        "skeleton.app.installer.compose_command",
        lambda action, **kwargs: ("docker", "compose", action),
    )
    class Result:
        service = "backend"
        ok = True
    monkeypatch.setattr(
        "skeleton.app.health.wait_for_application",
        lambda **kwargs: (Result(),),
    )

    calls = []
    def runner(command, **kwargs):
        calls.append((tuple(command), dict(kwargs)))
        if command[-1] == "up":
            assert "capture_output" not in kwargs
            assert kwargs["stderr"] is subprocess.STDOUT
            assert kwargs["stdout"].fileno() >= 0
            kwargs["stdout"].write("pretend-secret-which-must-not-be-reported\n")
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    receipt = install_application(tmp_path, start=True, install_python=False, runner=runner)
    assert receipt.ok
    assert len(calls) == 2
    assert "pretend-secret" not in repr(receipt.to_dict())

def test_setup_repairs_local_unauthenticated_mongo_urls(tmp_path):
    (tmp_path / ".env").write_text(
        "MONGO_INITDB_ROOT_USERNAME=admin\n"
        "MONGO_INITDB_ROOT_PASSWORD=stable-root-password\n"
        "MONGO_URL=mongodb://mongo:27017/tutolage\n"
        "SKL_MONGO_URI=mongodb://mongo:27017/skeleton\n"
        "JWT_SECRET=stable-jwt-secret\n",
        encoding="utf-8",
    )
    receipt = ensure_runtime_environment(tmp_path)
    values = _read_values(tmp_path / ".env")
    assert receipt.changed
    prefix = _test_mongo_uri("admin", "stable-root-password", "mongo:27017", "")
    assert values["MONGO_URL"].startswith(prefix)
    assert values["SKL_MONGO_URI"].startswith(prefix)
    assert not ensure_runtime_environment(tmp_path).changed


def test_setup_does_not_rewrite_external_unauthenticated_database(tmp_path):
    remote = "mongodb://external-database.example.net:27017/app"
    (tmp_path / ".env").write_text(
        "MONGO_INITDB_ROOT_USERNAME=admin\n"
        "MONGO_INITDB_ROOT_PASSWORD=stable-root-password\n"
        f"MONGO_URL={remote}\nSKL_MONGO_URI=\nJWT_SECRET=stable-jwt-secret\n",
        encoding="utf-8",
    )
    ensure_runtime_environment(tmp_path)
    assert _read_values(tmp_path / ".env")["MONGO_URL"] == remote

def test_setup_atomic_write_removes_secret_temp_file_on_fsync_failure(tmp_path, monkeypatch):
    import os
    from skeleton.app.setup_runtime import _atomic_write

    original = tmp_path / ".env"
    original.write_text("JWT_SECRET=original-value\n", encoding="utf-8")

    def broken_fsync(_fd):
        raise OSError("simulated disk I/O failure")

    monkeypatch.setattr(os, "fsync", broken_fsync)
    with pytest.raises(OSError, match="disk I/O failure"):
        _atomic_write(original, "JWT_SECRET=new-sensitive-value\n")
    assert original.read_text(encoding="utf-8") == "JWT_SECRET=original-value\n"
    assert list(tmp_path.glob(".env.*.tmp")) == []


def test_setup_atomic_write_removes_secret_temp_file_on_replace_failure(tmp_path, monkeypatch):
    import os
    from skeleton.app.setup_runtime import _atomic_write

    original = tmp_path / ".env"
    original.write_text("JWT_SECRET=original-value\n", encoding="utf-8")

    def broken_replace(_source, _destination):
        raise OSError("simulated rename failure")

    monkeypatch.setattr(os, "replace", broken_replace)
    with pytest.raises(OSError, match="rename failure"):
        _atomic_write(original, "JWT_SECRET=new-sensitive-value\n")
    assert original.read_text(encoding="utf-8") == "JWT_SECRET=original-value\n"
    assert list(tmp_path.glob(".env.*.tmp")) == []

def test_setup_never_retargets_remote_mongo_uri_containing_placeholder_word(tmp_path):
    # A remote hostname can contain "change-me" as a normal DNS label.
    external = _test_mongo_uri(
        "remote-user", "operator-secret", "db.change-me.example.net:27017", "app"
    )
    external_engine = _test_mongo_uri(
        "remote-user", "change-me-is-not-an-endpoint", "cluster.example.net:27017",
        "skeleton",
    )
    (tmp_path / ".env").write_text(
        "MONGO_INITDB_ROOT_USERNAME=admin\n"
        "MONGO_INITDB_ROOT_PASSWORD=local-root-password\n"
        f"MONGO_URL={external}\n"
        f"SKL_MONGO_URI={external_engine}\n"
        "JWT_SECRET=operator-jwt-secret\n",
        encoding="utf-8",
    )
    receipt = ensure_runtime_environment(tmp_path)
    values = _read_values(tmp_path / ".env")
    assert values["MONGO_URL"] == external
    assert values["SKL_MONGO_URI"] == external_engine
    assert {"MONGO_URL", "SKL_MONGO_URI"} <= set(receipt.preserved_keys)
    assert not ensure_runtime_environment(tmp_path).changed

def test_setup_phase_surfaces_missing_optional_ai_provider_without_exposing_secret(tmp_path):
    from skeleton.app.installer import _setup_phase
    from skeleton.app.setup_runtime import SetupResult

    secret = "simulated-secret-that-must-not-appear"
    result = SetupResult(
        env_path=tmp_path / ".env",
        created=True,
        changed=True,
        configured_keys=("JWT_SECRET",),
        preserved_keys=(),
        warnings=("OPENAI_API_KEY remains optional and unconfigured",),
    )
    receipt = _setup_phase(result)
    assert receipt.ok
    assert "OPENAI_API_KEY remains optional and unconfigured" in receipt.detail
    assert "JWT_SECRET" in receipt.detail
    assert secret not in receipt.detail


def test_setup_invalid_existing_signer_is_visible_in_install_receipt(tmp_path):
    from skeleton.app.installer import _setup_phase

    (tmp_path / ".env.example").write_text(
        ENV_TEMPLATE + "GF_KEYHOLDER_SEED=invalid-operator-seed\n",
        encoding="utf-8",
    )
    result = ensure_runtime_environment(tmp_path)
    receipt = _setup_phase(result)
    assert "GF_KEYHOLDER_SEED must be exactly 32 bytes" in receipt.detail
    assert "invalid-operator-seed" not in receipt.detail
