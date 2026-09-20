import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "scripts/check_contract_system.py"


def load_module():
    module_name = "check_contract_system_under_test"
    spec = importlib.util.spec_from_file_location(module_name, PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(module_name, None)
    return module


def test_contract_checker_path_is_repository_rooted():
    assert (ROOT / ".git").exists()
    assert PATH == ROOT / "scripts" / "check_contract_system.py"
    assert PATH.is_file()


def test_contract_manifest_is_unique_bounded_and_canonical():
    module = load_module()
    assert module.CHECKERS
    assert len(module.CHECKERS) == len(set(module.CHECKERS))
    assert len(module.CHECKERS) <= 16
    module._validate_manifest()
    for relative in module.CHECKERS:
        path, raw = module._admit_checker(relative)
        assert path.is_file()
        assert 0 < len(raw) <= module.MAX_CHECKER_BYTES


def test_contract_system_is_wired_into_merge_readiness():
    module = load_module()
    module._validate_wiring()


def test_checker_admission_rejects_symlink(tmp_path, monkeypatch):
    module = load_module()
    target = tmp_path / "check_fake_contract.py"
    target.write_text("raise SystemExit(0)\n", encoding="utf-8")
    link = tmp_path / "check_link_contract.py"
    link.symlink_to(target)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    with pytest.raises(RuntimeError):
        module._admit_checker("check_link_contract.py")


def test_checker_admission_rejects_forbidden_execution_marker(tmp_path, monkeypatch):
    module = load_module()
    checker = tmp_path / "scripts/check_fake_contract.py"
    checker.parent.mkdir()
    checker.write_text("eval('1')\n", encoding="utf-8")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    with pytest.raises(RuntimeError):
        module._admit_checker("scripts/check_fake_contract.py")


@pytest.mark.parametrize(
    "source",
    (
        "exec('pass')\n",
        "import os\nos.system('true')\n",
        "import subprocess\nsubprocess.run(['true'], shell=True)\n",
    ),
)
def test_checker_admission_rejects_executable_call_shapes(tmp_path, monkeypatch, source):
    module = load_module()
    checker = tmp_path / "scripts/check_fake_contract.py"
    checker.parent.mkdir()
    checker.write_text(source, encoding="utf-8")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    with pytest.raises(RuntimeError):
        module._admit_checker("scripts/check_fake_contract.py")


def test_checker_admission_allows_policy_marker_strings(tmp_path, monkeypatch):
    module = load_module()
    checker = tmp_path / "scripts/check_fake_contract.py"
    checker.parent.mkdir()
    checker.write_text("FORBIDDEN = ('eval(', 'exec(', 'shell=True')\n", encoding="utf-8")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    admitted, _ = module._admit_checker("scripts/check_fake_contract.py")
    assert admitted == checker


def test_contract_evidence_is_deterministic_shape():
    module = load_module()
    item = module.ContractEvidence(
        path="scripts/check_x_contract.py",
        sha256="a" * 64,
        bytes=10,
        returncode=0,
        stdout_tail="ok",
    )
    assert item.as_dict() == {
        "path": "scripts/check_x_contract.py",
        "sha256": "a" * 64,
        "bytes": 10,
        "returncode": 0,
        "stdout_tail": "ok",
    }
