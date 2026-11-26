"""Static callable dispatch and operator authorization regressions."""
from __future__ import annotations

import argparse

import pytest

from skeleton.perf_profiler import cli


def test_reviewed_callable_is_resolved():
    assert cli._resolve("gc:collect") is not None


@pytest.mark.parametrize("target", [
    "os:system", "json:loads", "gc:missing", "gc.collect",
    "gc:collect:extra", "bad-name:collect",
])
def test_unreviewed_or_malformed_target_rejected(target):
    with pytest.raises(cli.UsageError):
        cli._resolve(target)


def test_operator_gates_precede_callable_resolution(monkeypatch):
    monkeypatch.delenv("SKELETON_PERF_TRUSTED_EXECUTION", raising=False)
    monkeypatch.setenv("SKELETON_PERF_ALLOWED_TARGETS", "gc:collect")
    args = argparse.Namespace(allow_local_callable=True, target="gc:collect", top=0,
                              max_alloc_bytes=None, max_peak_bytes=None)
    with pytest.raises(cli.UsageError, match="trusted local operator"):
        cli._cmd_alloc(args)


def test_allowlist_gate_precedes_registry_resolution(monkeypatch):
    monkeypatch.setenv("SKELETON_PERF_TRUSTED_EXECUTION", "1")
    monkeypatch.setenv("SKELETON_PERF_ALLOWED_TARGETS", "gc:collect")
    args = argparse.Namespace(allow_local_callable=True, target="os:system", top=0,
                              max_alloc_bytes=None, max_peak_bytes=None)
    with pytest.raises(cli.UsageError, match="explicit trusted allowlist"):
        cli._cmd_alloc(args)
