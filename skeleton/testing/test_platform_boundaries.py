"""Route custody, public config, and observability hooks."""

from __future__ import annotations

import ast
from pathlib import Path

from skeleton.config.public_snapshot import PublicConfigError, public_settings_snapshot
from skeleton.observability.logging import StructuredLogger
from skeleton.observability.platform_hooks import MetricHook, log_event, trace_span

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _imports(relative: str) -> list[str]:
    tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
    found: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module:
            found.append(node.module)
        elif isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
    return found


def test_sidecar_and_command_routes_do_not_import_server_at_module_scope() -> None:
    for relative in ("skeleton/api/gameforge_routes.py", "skeleton/api/command_routes.py"):
        assert "skeleton.api.server" not in _imports(relative)
    assert "skeleton.api.command_routes" not in _imports("skeleton/api/gameforge_routes.py")


def test_harness_mounts_command_routes_not_the_gameforge_sidecar() -> None:
    text = (ROOT / "skeleton/deploy/harness.py").read_text(encoding="utf-8")
    assert "skeleton.api.command_routes" in text
    assert "gameforge_routes" not in text


def test_public_snapshot_rejects_secret_keys() -> None:
    class _Settings:
        def summary(self) -> dict[str, str]:
            return {"environment": "test", "service_token": "hidden"}

    with pytest.raises(PublicConfigError):
        public_settings_snapshot(_Settings())


def test_public_snapshot_accepts_a_redacted_summary() -> None:
    class _Settings:
        def summary(self) -> dict[str, str]:
            return {"environment": "test", "version": "16.0.0"}

    assert public_settings_snapshot(_Settings())["environment"] == "test"


def test_platform_hooks_log_trace_and_count() -> None:
    logger = StructuredLogger()
    event = log_event("INFO", "booted", logger=logger, component="engine")
    assert event.context["component"] == "engine"
    with trace_span("engine", "boot") as span:
        assert span.name == "boot"
    metrics = MetricHook()
    metrics.increment("requests")
    assert metrics.snapshot() == {"requests": 1}
