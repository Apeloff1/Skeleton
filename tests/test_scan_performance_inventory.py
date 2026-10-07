"""Fail-closed regressions for the scan-performance inventory (#969 S029)."""

from __future__ import annotations

import importlib.util
import json
import stat
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_scan_performance_inventory.py"
SPEC = importlib.util.spec_from_file_location("check_scan_performance_inventory", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
inventory = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = inventory
SPEC.loader.exec_module(inventory)

REPO_ROOT = Path(__file__).resolve().parents[1]

REPEATED_WALK = """
from pathlib import Path
ROOT = Path('.')
def scan():
    for path in ROOT.rglob('*.py'):
        print(path)
    for path in ROOT.rglob('*.md'):
        print(path)
"""

GIT_PER_FILE = """
import subprocess
from pathlib import Path
def _git(*args):
    return subprocess.run(['git', *args], check=False)
def inspect(paths):
    for path in paths:
        _git('check-attr', 'filter', '--', str(path))
"""

QUADRATIC_NESTED = """
from pathlib import Path
ROOT = Path('.')
def scan():
    for left in ROOT.rglob('*'):
        for right in ROOT.rglob('*'):
            pair = (left, right)
"""

QUADRATIC_BOUND_LIST = """
from pathlib import Path
ROOT = Path('.')
def scan():
    files = list(ROOT.rglob('*.py'))
    for left in files:
        for right in files:
            pair = (left, right)
"""

LINEAR_SINGLE = """
from pathlib import Path
ROOT = Path('.')
def scan():
    for path in ROOT.rglob('*.py'):
        print(path)
"""

LINEAR_GIT_ONCE = """
import subprocess
def tracked():
    return subprocess.run(['git', 'ls-files', '-z'], check=True).stdout
def inspect():
    for path in tracked().split(b'\\0'):
        print(path)
"""

REPEATED_VIA_HELPERS = """
from pathlib import Path
ROOT = Path('.')
def scan_py():
    for path in ROOT.rglob('*.py'):
        print(path)
def scan_md():
    for path in ROOT.rglob('*.md'):
        print(path)
def main():
    scan_py()
    scan_md()
"""

OPAQUE_DYNAMIC = """
import os
def scan(name):
    walker = getattr(os, name)
    return walker('.')
"""

SYNTAX_ERROR = "def scan(\n"


def _write(root: Path, relative: str, content: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _mini_repo(tmp_path: Path) -> Path:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "backend" / "scripts").mkdir(parents=True)
    return tmp_path


def test_task_identity_is_stable() -> None:
    assert inventory.TASK_ID == "reserve-S029-scan-performance-audit"
    assert inventory.CONFLICT_DOMAIN == "repo.readonly.scan_performance"
    assert inventory.INVENTORY_VERSION == 1
    assert inventory.EVIDENCE_KIND == "structural"
    assert "unknown" in inventory.CLASSIFICATIONS
    assert inventory.HOTSPOT_CLASSES == (
        "quadratic_nested_walk",
        "git_subprocess_per_file",
        "repeated_full_tree_walk",
    )


def test_fixture_repeated_full_tree_walk() -> None:
    record = inventory.classify_source(REPEATED_WALK, filename="scripts/repeated.py")
    assert record.classification == "repeated_full_tree_walk"
    assert record.timing is None
    assert any("repeated full-tree walks" in item for item in record.evidence)


def test_fixture_git_subprocess_per_file() -> None:
    record = inventory.classify_source(GIT_PER_FILE, filename="scripts/git_per_file.py")
    assert record.classification == "git_subprocess_per_file"
    assert any("git subprocess inside per-item loop" in item for item in record.evidence)


def test_fixture_quadratic_nested_walk() -> None:
    record = inventory.classify_source(QUADRATIC_NESTED, filename="scripts/quadratic.py")
    assert record.classification == "quadratic_nested_walk"
    assert any("nested" in item for item in record.evidence)


def test_fixture_quadratic_nested_iteration_over_walk_list() -> None:
    record = inventory.classify_source(QUADRATIC_BOUND_LIST, filename="scripts/quadratic_list.py")
    assert record.classification == "quadratic_nested_walk"


def test_fixture_linear_single_pass() -> None:
    record = inventory.classify_source(LINEAR_SINGLE, filename="scripts/linear.py")
    assert record.classification == "linear_single_pass"
    assert record.timing is None


def test_one_shot_git_listing_is_not_per_file() -> None:
    record = inventory.classify_source(LINEAR_GIT_ONCE, filename="scripts/git_once.py")
    assert record.classification == "linear_single_pass"


def test_repeated_walks_via_helpers_in_one_entry_point() -> None:
    record = inventory.classify_source(REPEATED_VIA_HELPERS, filename="scripts/helpers.py")
    assert record.classification == "repeated_full_tree_walk"


def test_syntax_error_is_unknown_fail_closed() -> None:
    record = inventory.classify_source(SYNTAX_ERROR, filename="scripts/broken.py")
    assert record.classification == "unknown"
    assert any("syntax error" in item for item in record.evidence)


def test_unreadable_file_is_unknown_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = _write(tmp_path, "scripts/blocked.py", LINEAR_SINGLE)

    def boom(self: Path, *args: object, **kwargs: object) -> str:
        raise PermissionError("sensitive path")

    monkeypatch.setattr(Path, "read_text", boom)
    record = inventory.classify_path(target, display="scripts/blocked.py")
    assert record.classification == "unknown"
    assert record.evidence == ("unreadable: PermissionError",)
    assert all("sensitive path" not in item for item in record.evidence)


def test_unreadable_fixture_tree_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _mini_repo(tmp_path)
    _write(root, "scripts/ok.py", LINEAR_SINGLE)
    _write(root, "backend/scripts/ok.py", LINEAR_SINGLE)
    blocked = root / "scripts" / "ok.py"

    original = Path.read_text

    def selective(self: Path, *args: object, **kwargs: object) -> str:
        if self.resolve() == blocked.resolve():
            raise PermissionError("hidden")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", selective)
    with pytest.raises(inventory.ScanPerformanceInventoryError, match="unclassified scanners"):
        inventory.assert_inventory_closed(root)


def test_missing_scan_root_fails_closed(tmp_path: Path) -> None:
    (tmp_path / "scripts").mkdir()
    with pytest.raises(inventory.ScanPerformanceInventoryError, match="required scan root missing"):
        inventory.collect_records(tmp_path)


def test_empty_scan_surface_fails_closed(tmp_path: Path) -> None:
    _mini_repo(tmp_path)
    with pytest.raises(inventory.ScanPerformanceInventoryError, match="zero Python files"):
        inventory.assert_inventory_closed(tmp_path)


def test_mini_repo_classifies_each_hotspot(tmp_path: Path) -> None:
    root = _mini_repo(tmp_path)
    _write(root, "scripts/repeated.py", REPEATED_WALK)
    _write(root, "scripts/git_per_file.py", GIT_PER_FILE)
    _write(root, "backend/scripts/quadratic.py", QUADRATIC_NESTED)
    _write(root, "backend/scripts/linear.py", LINEAR_SINGLE)

    report = inventory.assert_inventory_closed(root)
    by_path = {item["path"]: item for item in report["records"]}
    assert by_path["scripts/repeated.py"]["classification"] == "repeated_full_tree_walk"
    assert by_path["scripts/git_per_file.py"]["classification"] == "git_subprocess_per_file"
    assert by_path["backend/scripts/quadratic.py"]["classification"] == "quadratic_nested_walk"
    assert by_path["backend/scripts/linear.py"]["classification"] == "linear_single_pass"
    assert all(item["timing"] is None for item in report["records"])
    assert report["evidence_kind"] == "structural"


def test_tiny_fixture_measurement_matches_structural_class() -> None:
    linear = inventory.measure_tiny_fixture("linear_single_pass", n_files=4)
    repeated = inventory.measure_tiny_fixture("repeated_full_tree_walk", n_files=4)
    quadratic = inventory.measure_tiny_fixture("quadratic_nested_walk", n_files=4)
    git_loop = inventory.measure_tiny_fixture("git_subprocess_per_file", n_files=4)

    assert linear["visits"] == 4
    assert repeated["visits"] == 8
    assert quadratic["visits"] == 16
    assert git_loop["git_calls"] == 4
    assert all(item["timing"] is None for item in (linear, repeated, quadratic, git_loop))


def test_current_repo_report_is_deterministic_and_has_no_timings() -> None:
    first = inventory.assert_inventory_closed(REPO_ROOT)
    second = inventory.assert_inventory_closed(REPO_ROOT)
    encoded_first = json.dumps(first, sort_keys=True, separators=(",", ":"))
    encoded_second = json.dumps(second, sort_keys=True, separators=(",", ":"))
    assert encoded_first == encoded_second
    assert first["task_key"] == "reserve-S029-scan-performance-audit"
    assert first["conflict_domain"] == "repo.readonly.scan_performance"
    assert first["unknown_count"] == 0
    assert first["file_count"] > 0
    dumped = json.dumps(first)
    for banned in ("elapsed", "duration_ms", "seconds", "wall_clock", "runtime_ms"):
        assert banned not in dumped
    for record in first["records"]:
        assert record["timing"] is None
        assert record["classification"] in inventory.CLASSIFICATIONS
        assert "timing_ms" not in record
    paths = [record["path"] for record in first["records"]]
    assert paths == sorted(paths)
    assert any(path.endswith("check_scan_performance_inventory.py") for path in paths)
    self_record = next(
        record
        for record in first["records"]
        if record["path"].endswith("check_scan_performance_inventory.py")
    )
    assert self_record["classification"] == "linear_single_pass"


def test_current_repo_inventory_does_not_invent_measured_timings() -> None:
    report = inventory.inventory_report(REPO_ROOT)
    assert report["evidence_kind"] == "structural"
    for record in report["records"]:
        assert record["timing"] is None
        for item in record["evidence"]:
            assert "ms" not in item
            assert "seconds" not in item
            assert "elapsed" not in item


def test_opaque_dynamic_dispatch_is_unknown() -> None:
    record = inventory.classify_source(OPAQUE_DYNAMIC, filename="scripts/opaque.py")
    assert record.classification == "unknown"


def test_main_writes_json_and_succeeds_for_classified_repo(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _mini_repo(tmp_path)
    _write(root, "scripts/linear.py", LINEAR_SINGLE)
    _write(root, "backend/scripts/linear.py", LINEAR_SINGLE)
    assert inventory.main(["--root", str(root)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["unknown_count"] == 0
    assert payload["file_count"] == 2


def test_chmod_unreadable_directory_fails_closed(tmp_path: Path) -> None:
    root = _mini_repo(tmp_path)
    _write(root, "scripts/linear.py", LINEAR_SINGLE)
    hidden = root / "backend" / "scripts" / "hidden"
    hidden.mkdir()
    (hidden / "scan.py").write_text(LINEAR_SINGLE, encoding="utf-8")
    hidden.chmod(0)
    try:
        with pytest.raises(inventory.ScanPerformanceInventoryError, match="traversal failure|metadata failure"):
            inventory.collect_records(root)
    finally:
        hidden.chmod(stat.S_IRWXU)
