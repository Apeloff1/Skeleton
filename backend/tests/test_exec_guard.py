"""Regression tests for the fail-closed host execution boundary."""

from __future__ import annotations

import pytest

from core import exec_guard


_EXECUTION_ENV_VARS = (
    "ALLOW_UNSAFE_CODE_EXECUTION",
    "ALLOW_PRODUCTION_HOST_CODE_EXECUTION",
    "EMERGENT_DEPLOY",
    "ENVIRONMENT",
    "K_SERVICE",
    "KUBERNETES_SERVICE_HOST",
    "WEBSITE_INSTANCE_ID",
    "DYNO",
)


@pytest.fixture(autouse=True)
def clean_execution_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _EXECUTION_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_execution_disabled_by_default() -> None:
    assert exec_guard.code_execution_enabled() is False


def test_local_execution_requires_explicit_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALLOW_UNSAFE_CODE_EXECUTION", "true")
    assert exec_guard.code_execution_enabled() is True


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("EMERGENT_DEPLOY", "true"),
        ("ENVIRONMENT", "production"),
        ("K_SERVICE", "skeleton-api"),
        ("KUBERNETES_SERVICE_HOST", "10.0.0.1"),
        ("WEBSITE_INSTANCE_ID", "instance-1"),
        ("DYNO", "web.1"),
    ],
)
def test_production_markers_permanently_disable_host_execution(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    value: str,
) -> None:
    monkeypatch.setenv("ALLOW_UNSAFE_CODE_EXECUTION", "true")
    monkeypatch.setenv("ALLOW_PRODUCTION_HOST_CODE_EXECUTION", "true")
    monkeypatch.setenv(name, value)
    assert exec_guard.production_runtime_detected() is True
    assert exec_guard.code_execution_enabled() is False


def test_legacy_production_override_cannot_reenable_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("ALLOW_UNSAFE_CODE_EXECUTION", "true")
    monkeypatch.setenv("ALLOW_PRODUCTION_HOST_CODE_EXECUTION", "true")
    assert exec_guard.code_execution_enabled() is False


def test_false_like_production_flag_does_not_enable_production_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EMERGENT_DEPLOY", "false")
    assert exec_guard.production_runtime_detected() is False


def test_disabled_response_does_not_expose_configuration_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    response = exec_guard.execution_disabled_response("Python execution")
    assert response["ok"] is False
    assert response["disabled"] is True
    assert "Python execution" in response["error"]
    assert "ALLOW_UNSAFE_CODE_EXECUTION=true" not in response["error"]
    assert "ALLOW_PRODUCTION_HOST_CODE_EXECUTION" not in response["error"]


def test_production_disabled_message_requires_isolated_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    message = exec_guard.execution_disabled_message("C++ execution")
    assert "production application host" in message
    assert "isolated sandbox worker" in message
