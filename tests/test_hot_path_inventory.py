"""Fail-closed regressions for the hot-path inventory (#969 S152)."""

from __future__ import annotations

import importlib.util
import json
import stat
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_hot_path_inventory.py"
SPEC = importlib.util.spec_from_file_location("check_hot_path_inventory", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
inventory = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = inventory
SPEC.loader.exec_module(inventory)

REPO_ROOT = Path(__file__).resolve().parents[1]


MEASURED_BENCH = '''
import time
from typing import Any

def run_benchmark(*, iterations: int = 8) -> dict[str, Any]:
    started = time.perf_counter_ns()
    checksum = sum(range(iterations))
    elapsed_ns = time.perf_counter_ns() - started
    return {
        "evidence": {"checksum": checksum},
        "timing": {
            "elapsed_seconds": elapsed_ns / 1_000_000_000,
            "latency_gate": False,
        },
    }
'''

NAMED_BENCH_TEST = '''
from scripts.benchmark_widget import run_benchmark

def test_widget_benchmark_records_correctness_without_latency_gate():
    report = run_benchmark(iterations=4)
    assert report["evidence"]["checksum"] >= 0
    assert report["timing"]["latency_gate"] is False
'''

DOCUMENTED_ONLY = '''
"""Runtime snapshot.

Intentionally NO disk I/O on the hot path — every call must complete quickly.
"""

def snapshot() -> dict[str, int]:
    return {"ok": 1}
'''

NAMED_HOT_PATH_TEST = '''
"""Regression coverage for bounded retrieval hot-path state."""

def test_cache_is_bounded() -> None:
    assert True
'''

INVENTED_BENCHMARK = '''
import random

async def simulate_benchmark(request):
    """Hardware-accurate benchmark simulation."""
    times = [random.gauss(1.0, 0.1) for _ in range(8)]
    return {"total_time_ms": sum(times), "avg_time_ms": sum(times) / len(times)}
'''

SNAPSHOT_FALSE_POSITIVE = '''
def _snapshot_path(path: str) -> bool:
    return path.startswith("satellites/")
'''

SYNTAX_ERROR = "def run_benchmark(\n"

CATALOG_ONLY_UNDOCUMENTED = '''
def handle(request):
    return {"ok": True}
'''


def _write(root: Path, relative: str, content: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _mini_repo(tmp_path: Path) -> Path:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "skeleton").mkdir()
    (tmp_path / "backend").mkdir()
    return tmp_path


def _entry(
    path_id: str,
    path: str,
    symbol: str,
    evidence_files: tuple[str, ...] = (),
) -> inventory.CatalogEntry:
    return inventory.CatalogEntry(
        path_id=path_id,
        path=path,
        symbol=symbol,
        evidence_files=evidence_files,
    )


def test_task_identity_is_stable() -> None:
    assert inventory.TASK_ID == "reserve-S152-hot-path-inventory"
    assert inventory.CONFLICT_DOMAIN == "perf.readonly.hot_path_inventory"
    assert inventory.INVENTORY_VERSION == 1
    assert inventory.EVIDENCE_KIND == "structural"
    assert inventory.CLASSIFICATIONS == (
        "measured",
        "documented",
        "unknown_gap",
        "unknown",
    )
    assert inventory.SCAN_ROOTS == ("scripts", "skeleton", "backend")


def test_name_match_requires_hot_path_token_not_snapshot_path() -> None:
    assert inventory.name_matches_hot_path("hot_paths")
    assert inventory.name_matches_hot_path("run_benchmark")
    assert inventory.name_matches_hot_path("simulate_benchmark")
    assert inventory.name_matches_hot_path("hotpath")
    assert not inventory.name_matches_hot_path("_snapshot_path")
    assert not inventory.name_matches_hot_path("snapshot_path")
    assert not inventory.name_matches_hot_path("handle")


def test_measured_requires_named_evidence_or_recorded_metric() -> None:
    record = inventory.classify_source(
        MEASURED_BENCH,
        filename="scripts/benchmark_widget.py",
        symbol="run_benchmark",
        origin="catalog",
        proven_evidence=("skeleton/testing/test_widget_benchmark.py",),
    )
    assert record.classification == "measured"
    assert record.timing is None
    assert "timing" in record.metric_fields
    assert record.evidence_files == ("skeleton/testing/test_widget_benchmark.py",)


def test_recorded_metric_without_named_file_is_still_measured() -> None:
    record = inventory.classify_source(
        MEASURED_BENCH,
        filename="scripts/benchmark_widget.py",
        symbol="run_benchmark",
        origin="ast",
    )
    assert record.classification == "measured"
    assert any("recorded metric field" in item for item in record.evidence)
    assert record.timing is None


def test_documented_only_is_not_measured() -> None:
    record = inventory.classify_source(
        DOCUMENTED_ONLY,
        filename="backend/core/runtime_health.py",
        symbol="snapshot",
        origin="catalog",
        path_id="backend.runtime_health.snapshot",
    )
    assert record.classification == "documented"
    assert record.metric_fields == ()
    assert record.evidence_files == ()
    assert any("documented hot path" in item for item in record.evidence)


def test_invented_random_benchmark_is_not_measured() -> None:
    record = inventory.classify_source(
        INVENTED_BENCHMARK,
        filename="backend/routes/compiler_tools.py",
        symbol="simulate_benchmark",
        origin="ast",
    )
    assert record.classification == "unknown_gap"
    assert record.metric_fields == ()
    assert record.timing is None


def test_syntax_error_is_unknown_fail_closed() -> None:
    record = inventory.classify_source(
        SYNTAX_ERROR,
        filename="scripts/broken.py",
        symbol="run_benchmark",
        origin="ast",
    )
    assert record.classification == "unknown"
    assert any("syntax error" in item for item in record.evidence)


def test_unreadable_file_is_unknown_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = _write(tmp_path, "scripts/blocked.py", MEASURED_BENCH)

    def boom(self: Path, *args: object, **kwargs: object) -> str:
        raise PermissionError("sensitive path")

    monkeypatch.setattr(Path, "read_text", boom)
    record = inventory.classify_path(
        target,
        display="scripts/blocked.py",
        symbol="run_benchmark",
        origin="ast",
    )
    assert record.classification == "unknown"
    assert record.evidence == ("unreadable: PermissionError",)
    assert all("sensitive path" not in item for item in record.evidence)


def test_unreadable_tree_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _mini_repo(tmp_path)
    _write(root, "scripts/ok.py", "def idle():\n    return 1\n")
    _write(root, "skeleton/ok.py", "def idle():\n    return 1\n")
    _write(root, "backend/ok.py", "def idle():\n    return 1\n")
    blocked = root / "scripts" / "ok.py"
    original = Path.read_text

    def selective(self: Path, *args: object, **kwargs: object) -> str:
        if self.resolve() == blocked.resolve():
            raise PermissionError("hidden")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", selective)
    catalog = (_entry("idle.ok", "skeleton/ok.py", "idle"),)
    with pytest.raises(inventory.HotPathInventoryError, match="unclassified hot paths"):
        inventory.assert_inventory_closed(root, catalog=catalog)


def test_missing_scan_root_fails_closed(tmp_path: Path) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "skeleton").mkdir()
    with pytest.raises(inventory.HotPathInventoryError, match="required scan root missing"):
        inventory.collect_records(tmp_path, catalog=())


def test_missing_catalog_path_fails_closed(tmp_path: Path) -> None:
    root = _mini_repo(tmp_path)
    _write(root, "scripts/ok.py", "def idle():\n    return 1\n")
    catalog = (_entry("missing.path", "skeleton/missing.py", "run_benchmark"),)
    with pytest.raises(inventory.HotPathInventoryError, match="unclassified hot paths"):
        inventory.assert_inventory_closed(root, catalog=catalog)


def test_mini_repo_classifies_measured_documented_and_gap(tmp_path: Path) -> None:
    root = _mini_repo(tmp_path)
    _write(root, "scripts/benchmark_widget.py", MEASURED_BENCH)
    _write(root, "skeleton/testing/test_widget_benchmark.py", NAMED_BENCH_TEST)
    _write(root, "skeleton/testing/test_retrieval_hot_path.py", NAMED_HOT_PATH_TEST)
    _write(root, "skeleton/retrieval/cache.py", "class ResultCache:\n    pass\n")
    _write(root, "backend/core/runtime_health.py", DOCUMENTED_ONLY)
    _write(root, "backend/routes/compiler_tools.py", INVENTED_BENCHMARK)
    _write(root, "scripts/helpers.py", SNAPSHOT_FALSE_POSITIVE)

    catalog = (
        _entry(
            "frontier.widget",
            "scripts/benchmark_widget.py",
            "run_benchmark",
            ("skeleton/testing/test_widget_benchmark.py",),
        ),
        _entry(
            "retrieval.cache",
            "skeleton/retrieval/cache.py",
            "ResultCache",
            ("skeleton/testing/test_retrieval_hot_path.py",),
        ),
        _entry("health.snapshot", "backend/core/runtime_health.py", "snapshot"),
        _entry("gateway.handle", "scripts/helpers.py", "handle"),
    )

    report = inventory.assert_inventory_closed(root, catalog=catalog)
    by_key = {(item["path"], item["symbol"]): item for item in report["records"]}

    assert by_key[("scripts/benchmark_widget.py", "run_benchmark")]["classification"] == "measured"
    assert by_key[("skeleton/retrieval/cache.py", "ResultCache")]["classification"] == "measured"
    assert by_key[("backend/core/runtime_health.py", "snapshot")]["classification"] == "documented"
    assert by_key[("backend/routes/compiler_tools.py", "simulate_benchmark")]["classification"] == "unknown_gap"
    assert ("scripts/helpers.py", "_snapshot_path") not in by_key
    assert by_key[("scripts/helpers.py", "handle")]["classification"] == "unknown_gap"
    assert all(item["timing"] is None for item in report["records"])
    assert report["unknown_count"] == 0
    assert report["evidence_kind"] == "structural"


def test_tiny_fixture_measures_bounded_visits_not_wall_clock() -> None:
    measured = inventory.measure_tiny_fixture(n_files=4)
    assert measured["visits"] == 4
    assert measured["timing"] == {"bounded_visits": 4}
    assert "elapsed" not in json.dumps(measured)
    assert "duration_ms" not in json.dumps(measured)


def test_current_repo_report_is_deterministic_and_has_no_invented_timings() -> None:
    first = inventory.assert_inventory_closed(REPO_ROOT)
    second = inventory.assert_inventory_closed(REPO_ROOT)
    encoded_first = json.dumps(first, sort_keys=True, separators=(",", ":"))
    encoded_second = json.dumps(second, sort_keys=True, separators=(",", ":"))
    assert encoded_first == encoded_second
    assert first["task_id"] == "reserve-S152-hot-path-inventory"
    assert first["conflict_domain"] == "perf.readonly.hot_path_inventory"
    assert first["unknown_count"] == 0
    assert first["candidate_count"] > 0
    assert first["measured_count"] > 0
    assert first["documented_count"] > 0
    dumped = json.dumps(first)
    assert '"timing": null' in dumped
    assert "wall_clock" not in dumped
    assert "runtime_ms" not in dumped
    assert "bounded_visits" not in dumped
    for record in first["records"]:
        assert record["timing"] is None
        assert record["classification"] in inventory.CLASSIFICATIONS
        assert "timing_ms" not in record
    paths = [record["path"] for record in first["records"]]
    assert paths == sorted(paths)
    assert not any(path.endswith("check_hot_path_inventory.py") for path in paths)
    assert not any(path.endswith("check_scan_performance_inventory.py") for path in paths)


def test_current_repo_does_not_classify_snapshot_path_as_hot_path() -> None:
    report = inventory.inventory_report(REPO_ROOT)
    symbols = {(item["path"], item["symbol"]) for item in report["records"]}
    assert ("skeleton/automation/dependabot_merge_policy.py", "_snapshot_path") not in symbols


def test_current_repo_frontier_benchmarks_are_measured() -> None:
    report = inventory.inventory_report(REPO_ROOT)
    by_key = {(item["path"], item["symbol"]): item for item in report["records"]}
    bait = by_key[("scripts/benchmark_frontier_bait.py", "run_benchmark")]
    assert bait["classification"] == "measured"
    assert "skeleton/testing/test_frontier_bait_benchmark.py" in bait["evidence_files"]
    health = by_key[("backend/core/runtime_health.py", "snapshot")]
    assert health["classification"] == "documented"
    cache = by_key[("skeleton/retrieval/cache.py", "ResultCache")]
    assert cache["classification"] == "measured"


def test_current_repo_simulated_compiler_benchmark_is_a_gap() -> None:
    report = inventory.inventory_report(REPO_ROOT)
    by_key = {(item["path"], item["symbol"]): item for item in report["records"]}
    simulated = by_key[("backend/routes/compiler_tools.py", "simulate_benchmark")]
    assert simulated["classification"] == "unknown_gap"
    assert simulated["timing"] is None
    assert simulated["metric_fields"] == []


def test_main_writes_json_and_succeeds_for_classified_repo(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _mini_repo(tmp_path)
    _write(root, "scripts/benchmark_widget.py", MEASURED_BENCH)
    _write(root, "skeleton/ok.py", "def idle():\n    return 1\n")
    _write(root, "backend/ok.py", "def idle():\n    return 1\n")
    _write(root, "skeleton/testing/test_widget_benchmark.py", NAMED_BENCH_TEST)
    catalog = (
        _entry(
            "frontier.widget",
            "scripts/benchmark_widget.py",
            "run_benchmark",
            ("skeleton/testing/test_widget_benchmark.py",),
        ),
    )
    monkeypatch.setattr(inventory, "HOT_PATH_CATALOG", catalog)
    assert inventory.main(["--root", str(root)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["unknown_count"] == 0
    assert payload["measured_count"] >= 1
    assert payload["task_id"] == "reserve-S152-hot-path-inventory"


def test_chmod_unreadable_directory_fails_closed(tmp_path: Path) -> None:
    root = _mini_repo(tmp_path)
    _write(root, "scripts/ok.py", "def idle():\n    return 1\n")
    hidden = root / "backend" / "hidden"
    hidden.mkdir()
    (hidden / "scan.py").write_text("def run_benchmark():\n    return 1\n", encoding="utf-8")
    hidden.chmod(0)
    try:
        with pytest.raises(inventory.HotPathInventoryError, match="traversal failure|metadata failure"):
            inventory.collect_records(
                root, catalog=(_entry("idle.ok", "scripts/ok.py", "idle"),)
            )
    finally:
        hidden.chmod(stat.S_IRWXU)


def test_does_not_use_scan_performance_classes() -> None:
    assert "repeated_full_tree_walk" not in inventory.CLASSIFICATIONS
    assert "git_subprocess_per_file" not in inventory.CLASSIFICATIONS
    assert "quadratic_nested_walk" not in inventory.CLASSIFICATIONS
    assert "linear_single_pass" not in inventory.CLASSIFICATIONS
    assert "network-required" not in inventory.CLASSIFICATIONS
    assert "covered" not in inventory.CLASSIFICATIONS
    assert "missing" not in inventory.CLASSIFICATIONS
