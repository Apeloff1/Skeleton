"""Isolated executable proofs for the node-forge RSA security installation patch."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
PATCHER = ROOT / "frontend/scripts/patch-node-modules.js"
NODE = shutil.which("node")

VULNERABLE = (
    "function verify(obj, digestInfoValidator, capture, errors) {\n"
    "  if(!asn1.validate(obj, digestInfoValidator, capture, errors) ||\n"
    "    obj.value.length !== 2) {\n"
    '    throw new Error("invalid DigestInfo");\n'
    "  }\n"
    "}\n"
)


def _install_fixture(tmp_path: Path, *, version: str, source: str) -> tuple[Path, Path]:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copyfile(PATCHER, scripts / "patch-node-modules.js")
    library = tmp_path / "node_modules/node-forge"
    (library / "lib").mkdir(parents=True)
    (library / "package.json").write_text(
        json.dumps({"version": version}), encoding="utf-8"
    )
    rsa = library / "lib/rsa.js"
    rsa.write_text(source, encoding="utf-8")
    return scripts / "patch-node-modules.js", rsa


def _run(script: Path) -> subprocess.CompletedProcess[str]:
    assert NODE, "Node.js is required to verify the frontend RSA patch gate"
    return subprocess.run(
        [NODE, str(script)],
        check=False,
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize("version", ["1.4.0", "1.4.2"])
def test_exact_reviewed_node_forge_versions_are_hardened_idempotently(
    tmp_path: Path, version: str
) -> None:
    script, rsa = _install_fixture(tmp_path, version=version, source=VULNERABLE)
    first = _run(script)
    assert first.returncode == 0, first.stderr
    result = rsa.read_text(encoding="utf-8")
    assert "obj.value[0].value.length !==" in result
    assert "(('parameters' in capture) ? 2 : 1)" in result
    assert "if(!asn1.validate" in result
    assert "obj.value.length !== 2 ||" in result

    second = _run(script)
    assert second.returncode == 0, second.stderr
    assert rsa.read_text(encoding="utf-8") == result


def test_unreviewed_node_forge_version_fails_closed(tmp_path: Path) -> None:
    script, rsa = _install_fixture(tmp_path, version="1.4.3", source=VULNERABLE)
    result = _run(script)
    assert result.returncode != 0
    assert "requires security patch review" in result.stderr
    assert rsa.read_text(encoding="utf-8") == VULNERABLE


def test_unknown_node_forge_source_shape_fails_closed(tmp_path: Path) -> None:
    source = "function verify() { return true; }\n"
    script, rsa = _install_fixture(tmp_path, version="1.4.2", source=source)
    result = _run(script)
    assert result.returncode != 0
    assert "security target changed shape" in result.stderr
    assert rsa.read_text(encoding="utf-8") == source


def test_mixed_node_forge_patch_states_fail_closed(tmp_path: Path) -> None:
    source = VULNERABLE + "obj.value[0].value.length !== 2;\n"
    script, rsa = _install_fixture(tmp_path, version="1.4.2", source=source)
    result = _run(script)
    assert result.returncode != 0
    assert "mixed DigestInfo patch states" in result.stderr
    assert rsa.read_text(encoding="utf-8") == source
