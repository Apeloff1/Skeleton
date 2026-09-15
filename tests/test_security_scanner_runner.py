from __future__ import annotations

import subprocess
import sys

import scripts.run_security_scanners as runner


def test_canonical_scanner_manifest_is_nonempty_unique_and_resolves() -> None:
    assert runner.CANONICAL_SCANNERS
    assert len(runner.CANONICAL_SCANNERS) == len(set(runner.CANONICAL_SCANNERS))
    for scanner in runner.CANONICAL_SCANNERS:
        resolved = runner._resolve_scanner(scanner)
        assert resolved.is_file()
        assert resolved.suffix == ".py"


def test_run_scanner_uses_exact_python_argv_without_shell(monkeypatch) -> None:
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    scanner = runner.CANONICAL_SCANNERS[0]

    assert runner.run_scanner(scanner, timeout=3.0) == 0
    resolved = runner._resolve_scanner(scanner)
    assert calls == [
        (
            [sys.executable, str(resolved)],
            {
                "cwd": runner.REPO_ROOT,
                "check": False,
                "timeout": 3.0,
            },
        )
    ]


def test_nonzero_scanner_exit_fails_closed(monkeypatch) -> None:
    def fake_run(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 7)

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    assert runner.run_scanner(runner.CANONICAL_SCANNERS[0]) == 1


def test_signal_terminated_scanner_fails_closed(monkeypatch) -> None:
    def fake_run(argv, **kwargs):
        return subprocess.CompletedProcess(argv, -9)

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    assert runner.run_scanner(runner.CANONICAL_SCANNERS[0]) == 1


def test_timeout_fails_closed(monkeypatch) -> None:
    def fake_run(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, kwargs["timeout"])

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    assert runner.run_scanner(runner.CANONICAL_SCANNERS[0], timeout=0.5) == 124


def test_launch_error_fails_closed(monkeypatch) -> None:
    def fake_run(argv, **kwargs):
        raise OSError("exec failed")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    assert runner.run_scanner(runner.CANONICAL_SCANNERS[0]) == 126


def test_missing_or_escaping_scanner_path_fails_closed() -> None:
    assert runner.run_scanner("backend/scripts/does-not-exist.py") == 2
    assert runner.run_scanner("../outside.py") == 2


def test_empty_suite_cannot_report_success() -> None:
    assert runner.run_suite(()) == 2


def test_suite_stops_at_first_failed_scanner(monkeypatch) -> None:
    seen = []

    def fake_run_scanner(scanner, *, timeout):
        seen.append(scanner)
        return 1 if len(seen) == 2 else 0

    monkeypatch.setattr(runner, "run_scanner", fake_run_scanner)
    scanners = runner.CANONICAL_SCANNERS[:3]

    assert runner.run_suite(scanners, timeout=9.0) == 1
    assert seen == list(scanners[:2])
