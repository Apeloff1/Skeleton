"""Read-only orphan inventory and third-wave operator command regressions."""
from __future__ import annotations

import configparser
from pathlib import Path
import sys
import tomllib
from types import ModuleType

import pytest

from skeleton.__main__ import main
from skeleton.app.orphan_cli_audit import AuditError, ScanBudget, scan

ROOT = Path(__file__).resolve().parents[2]
OWNERS = (
    ("jeeves-desktop-campaign-delivery", "skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_campaign_delivery_cli"),
    ("jeeves-desktop-capsule-transport", "skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_capsule_transport_cli"),
    ("jeeves-desktop-capsule-verify", "skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_capsule_verifier_cli"),
    ("jeeves-desktop-native-campaign", "skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_native_campaign_cli"),
    ("jeeves-desktop-native-capsule", "skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_native_capsule_cli"),
    ("jeeves-desktop-native-code", "skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_native_code_cli"),
    ("jeeves-desktop-native-proposal", "skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_native_proposal_cli"),
    ("jeeves-desktop-source-delivery", "skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_native_source_delivery_cli"),
    ("jeeves-desktop-work", "skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_work_cli"),
    ("local-deployment-qualification", "skeleton.ai.runtime.operational_ai.deployment.qualification.cli"),
    ("local-model-install", "skeleton.ai.runtime.operational_ai.deployment.install.cli"),
    ("local-production-request", "skeleton.ai.runtime.operational_ai.deployment.production.cli"),
    ("orphan-cli-audit", "skeleton.app.orphan_cli_audit"),
)


@pytest.mark.parametrize("command,module", OWNERS)
def test_same_route_and_console_owner(monkeypatch, command, module):
    calls = []
    owner = ModuleType(module)
    def execute(argv):
        calls.append(argv)
        return 17
    owner.main = execute
    monkeypatch.setitem(sys.modules, module, owner)
    assert main([command, "--owner-option", "literal"]) == 17
    assert calls == [["--owner-option", "literal"]]
    if not (ROOT / "pyproject.toml").is_file():
        return
    modern = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read(ROOT / "setup.cfg", encoding="utf-8")
    legacy = dict(line.strip().split(" = ", 1) for line in
                  cfg["options.entry_points"]["console_scripts"].splitlines() if line.strip())
    script = "skeleton-" + command
    assert modern["project"]["scripts"][script] == legacy[script] == module + ":main"


def fixture_root(tmp_path):
    pkg = tmp_path / "skeleton"
    pkg.mkdir()
    (pkg / "__main__.py").write_text(
        "from skeleton.live_cli import main\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[project.scripts]\nlive = "skeleton.live_cli:main"\n'
        'drift = "skeleton.drift_cli:main"\n', encoding="utf-8")
    (tmp_path / "setup.cfg").write_text(
        "[options.entry_points]\nconsole_scripts =\n"
        "  live = skeleton.live_cli:main\n", encoding="utf-8")
    for name, content in {
        "live_cli.py": "def main(argv=None): pass\n",
        "drift_cli.py": "def main(argv=None): pass\n",
        "orphan_cli.py": "raise AssertionError('must never import')\ndef main(argv=None): pass\n",
        "other_cli.py": "def main(): pass\n",
        "not_cli.py": "def helper(): pass\n",
        "broken_cli.py": "def something(:\n",
    }.items():
        (pkg / name).write_text(content, encoding="utf-8")
    return tmp_path


def test_inventory_classifies_source_without_execution(tmp_path):
    root = fixture_root(tmp_path)
    result = scan(root)
    groups = {item["module"]: item for item in result["candidates"]}
    assert groups["skeleton.live_cli"]["classification"] == "console_and_root_reference"
    assert groups["skeleton.drift_cli"]["classification"] == "metadata_drift"
    assert groups["skeleton.orphan_cli"]["classification"] == "unregistered_argv_candidate"
    assert groups["skeleton.other_cli"]["classification"] == "unregistered_other_signature"
    assert len(groups["skeleton.orphan_cli"]["source_sha256"]) == 64
    assert not result["runtime_reachability_verified"]
    assert not result["execution_authorized"]
    assert not result["complete"]
    assert any(item["path"].endswith("broken_cli.py") for item in result["issues"])


def test_limits_and_symlinks_do_not_claim_complete_inventory(tmp_path):
    root = fixture_root(tmp_path)
    (root / "skeleton" / "broken_cli.py").unlink()
    try:
        (root / "skeleton" / "alias_cli.py").symlink_to(root / "skeleton" / "orphan_cli.py")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    full = scan(root)
    assert full["skipped_symlinks"] == 1
    assert not full["complete"]
    assert not any(c["module"] == "skeleton.alias_cli" for c in full["candidates"])
    limited = scan(root, budget=ScanBudget(max_entries=1))
    assert limited["entry_limit_reached"]
    assert not limited["complete"]


def test_budget_bounds():
    with pytest.raises(AuditError):
        ScanBudget(max_candidates=0)
    with pytest.raises(AuditError):
        ScanBudget(max_file_bytes=2**40)


def test_audit_command_real_cli_reports_incomplete(tmp_path, capsys):
    root = fixture_root(tmp_path)
    assert main(["orphan-cli-audit", "--root", str(root), "--candidates-only"]) == 3
    import json
    response = json.loads(capsys.readouterr().out)
    assert all(c["classification"].startswith("unregistered_") or
               c["classification"] == "metadata_drift" for c in response["candidates"])


def test_explicitly_bound_non_cli_filename_is_included(tmp_path):
    root = fixture_root(tmp_path)
    owner = root / "skeleton" / "custom_owner.py"
    owner.write_text("def main(argv=None): pass\n", encoding="utf-8")
    with (root / "pyproject.toml").open("a", encoding="utf-8") as stream:
        stream.write('custom = "skeleton.custom_owner:main"\n')
    with (root / "setup.cfg").open("a", encoding="utf-8") as stream:
        stream.write("  custom = skeleton.custom_owner:main\n")
    result = scan(root)
    record, = [item for item in result["candidates"]
               if item["module"] == "skeleton.custom_owner"]
    assert record["classification"] == "console_only"


def test_candidate_ceiling_has_distinct_reason(tmp_path):
    root = fixture_root(tmp_path)
    result = scan(root, budget=ScanBudget(max_candidates=1))
    assert not result["complete"]
    assert result["limit_reason"] == "max_candidates"
    assert not result["entry_limit_reached"]


def test_invalid_toml_is_structured_rejection(tmp_path, capsys):
    root = fixture_root(tmp_path)
    (root / "pyproject.toml").write_text("[project.scripts", encoding="utf-8")
    assert main(["orphan-cli-audit", "--root", str(root)]) == 2
    import json
    assert json.loads(capsys.readouterr().err)["complete"] is False
