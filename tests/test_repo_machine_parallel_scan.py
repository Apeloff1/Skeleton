"""Bounded concurrent repository scanning retains exact deterministic results."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock
from time import sleep

from skeleton.repo_machine.builder import RepositoryModelBuilder


CONFIG = """
[repository]
schema_version = 1
name = "parallel-scan-test"
max_files = 256
max_file_bytes = 100000
max_context_bytes = 10000
[policy]
detect_dependency_cycles = true
require_tests_for_code = false
detect_oversized_modules = false
[[zone]]
name = "app"
prefixes = ["app/"]
owner = "verification"
criticality = "high"
"""


def _fixture(root: Path) -> None:
    (root / ".machine").mkdir()
    (root / ".machine" / "repository.toml").write_text(CONFIG, encoding="utf-8")
    (root / "app").mkdir()
    for index in range(21):
        module = f"m{index:02d}"
        dependency = f"import app.m{index - 1:02d}\n" if index else ""
        (root / "app" / f"{module}.py").write_text(
            dependency + f"VALUE = {index}\n", encoding="utf-8",
        )


def test_parallel_inventory_matches_sequential_records_and_fingerprint() -> None:
    with TemporaryDirectory() as temp:
        root = Path(temp)
        _fixture(root)
        scanner = RepositoryModelBuilder(root)
        paths, truncated = scanner._iter_files()
        assert not truncated
        expected = tuple(sorted(
            (scanner._record(path) for path in paths),
            key=lambda item: item.path,
        ))
        first = scanner.build()
        second = scanner.build()
        assert first.files == expected
        assert second.files == expected
        assert first.fingerprint == second.fingerprint
        assert first.edges == second.edges
        assert first.findings == second.findings


def test_scan_concurrency_is_bounded_and_source_errors_are_fail_closed(monkeypatch) -> None:
    with TemporaryDirectory() as temp:
        root = Path(temp)
        _fixture(root)
        scanner = RepositoryModelBuilder(root)
        original = scanner._record
        lock = Lock()
        state = {"active": 0, "peak": 0}

        def observed(path: Path):
            with lock:
                state["active"] += 1
                state["peak"] = max(state["peak"], state["active"])
            try:
                sleep(0.015)
                if path.name == "m07.py":
                    raise OSError("file inaccessible")
                return original(path)
            finally:
                with lock:
                    state["active"] -= 1

        monkeypatch.setattr(scanner, "_record", observed)
        model = scanner.build()
        assert 2 <= state["peak"] <= 8
        assert any(
            finding.code == "scan.unreadable" and finding.path == "app/m07.py"
            for finding in model.findings
        )
        assert all(record.path != "app/m07.py" for record in model.files)
