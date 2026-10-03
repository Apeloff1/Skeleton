"""Regression tests for the pinned toolchain bootstrap contract (#807 B004)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "verify_toolchain_bootstrap.py"
SPEC = importlib.util.spec_from_file_location("verify_toolchain_bootstrap", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
bootstrap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bootstrap)


def _runner(overrides: dict[tuple[str, ...], str] | None = None):
    outputs = {
        ("python", "--version"): "Python 3.11.16",
        ("node", "--version"): "v24.20.0",
        ("uv", "--version"): "uv 0.12.15 (f00dbabe 2026-09-01)",
        ("git", "--version"): "git version 2.51.0",
        ("java", "-version"): 'openjdk version "21.0.8" 2026-07-15',
        ("mise", "--version"): "2026.9.10 linux-x64",
    }
    if overrides:
        outputs.update(overrides)

    def run(command):
        key = tuple(command)
        if key not in outputs:
            raise AssertionError(f"unexpected command: {key}")
        return outputs[key]

    return run


def test_repository_bootstrap_contract_is_self_consistent() -> None:
    manifest, mise = bootstrap.load_contract()

    assert manifest["bootstrap_command"] == "mise run bootstrap"
    assert manifest["installed_toolchains"] == {
        "python": "3.11.16",
        "node": "24.20.0",
        "uv": "0.12.15",
    }
    assert mise["tools"] == manifest["installed_toolchains"]
    assert mise["tasks"]["bootstrap"]["run"] == [
        "mise install",
        "mise exec -- python scripts/verify_toolchain_bootstrap.py",
    ]


def test_environment_verification_returns_bounded_evidence() -> None:
    manifest, _mise = bootstrap.load_contract()

    evidence = bootstrap.verify_environment(
        manifest,
        runner=_runner(),
        system_name="Linux",
        machine_name="x86_64",
    )

    assert evidence["toolchains"] == manifest["installed_toolchains"]
    assert evidence["git_version"] == "2.51.0"
    assert evidence["java_major"] == 21
    assert evidence["system"] == "Linux"
    assert evidence["architecture"] == "x86_64"
    assert evidence["bootstrap_command"] == "mise run bootstrap"
    assert "2026.9.10" in evidence["mise_version"]


@pytest.mark.parametrize(
    ("command", "output", "message"),
    [
        (("python", "--version"), "Python 3.11.15", "python version mismatch"),
        (("node", "--version"), "v22.0.0", "node version mismatch"),
        (("uv", "--version"), "uv 0.12.14", "uv version mismatch"),
        (("git", "--version"), "git version 2.39.5", "below bootstrap minimum"),
        (("java", "-version"), 'openjdk version "17.0.12"', "Java major"),
    ],
)
def test_version_drift_fails_closed(
    command: tuple[str, ...],
    output: str,
    message: str,
) -> None:
    manifest, _mise = bootstrap.load_contract()

    with pytest.raises(bootstrap.ToolchainBootstrapError, match=message):
        bootstrap.verify_environment(
            manifest,
            runner=_runner({command: output}),
            system_name="Linux",
            machine_name="x86_64",
        )


@pytest.mark.parametrize(
    ("system_name", "machine_name", "message"),
    [
        ("FreeBSD", "x86_64", "unsupported host system"),
        ("Linux", "mips64", "unsupported host architecture"),
    ],
)
def test_unsupported_host_fails_closed(
    system_name: str,
    machine_name: str,
    message: str,
) -> None:
    manifest, _mise = bootstrap.load_contract()

    with pytest.raises(bootstrap.ToolchainBootstrapError, match=message):
        bootstrap.verify_environment(
            manifest,
            runner=_runner(),
            system_name=system_name,
            machine_name=machine_name,
        )


def test_mise_and_manifest_pin_drift_fails_closed(tmp_path: Path) -> None:
    manifest = json.loads(bootstrap.MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    mise = bootstrap.MISE_PATH.read_text(encoding="utf-8").replace(
        'node = "24.20.0"',
        'node = "24.19.0"',
    )
    mise_path = tmp_path / "mise.toml"
    mise_path.write_text(mise, encoding="utf-8")

    with pytest.raises(bootstrap.ToolchainBootstrapError, match="node pin"):
        bootstrap.load_contract(manifest_path, mise_path)


def test_bootstrap_task_sequence_drift_fails_closed(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        bootstrap.MANIFEST_PATH.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    mise = bootstrap.MISE_PATH.read_text(encoding="utf-8").replace(
        '"mise install",',
        '"echo skip-install",',
    )
    mise_path = tmp_path / "mise.toml"
    mise_path.write_text(mise, encoding="utf-8")

    with pytest.raises(bootstrap.ToolchainBootstrapError, match="task command"):
        bootstrap.load_contract(manifest_path, mise_path)


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        ('openjdk version "21.0.8" 2026-07-15', 21),
        ('java version "22.0.1" 2026-01-01', 22),
        ("openjdk 23.0.2 2026-04-16", 23),
    ],
)
def test_java_major_parser(output: str, expected: int) -> None:
    assert bootstrap._java_major(output) == expected


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        ("git version 2.40.0", (2, 40, 0)),
        ("git version 2.51", (2, 51)),
        ("git version 3.0.1.windows.1", (3, 0, 1)),
    ],
)
def test_git_version_parser(output: str, expected: tuple[int, ...]) -> None:
    assert bootstrap._git_version(output) == expected
