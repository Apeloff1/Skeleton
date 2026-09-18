"""Lock app error surfaces onto the shared safeError helper."""
from __future__ import annotations

from pathlib import Path


FRONTEND = Path(__file__).resolve().parents[1] / "frontend"


def test_safe_error_helper_exists() -> None:
    source = (FRONTEND / "utils" / "safeError.ts").read_text(encoding="utf-8")
    assert "export function redactSecrets" in source
    assert "export function crashTelemetryFields" in source
    assert "export function isDevErrorDetails" in source
    assert "Bearer [REDACTED]" in source


def test_error_boundary_does_not_post_raw_stacks() -> None:
    source = (FRONTEND / "components" / "ErrorBoundary.tsx").read_text(encoding="utf-8")
    assert "crashTelemetryFields" in source
    assert "isDevErrorDetails" in source
    assert "error.message," not in source
    assert "(error.stack || '').slice(0, 8000)" not in source


def test_error_state_hides_details_outside_dev() -> None:
    source = (FRONTEND / "components" / "ui" / "ErrorState.tsx").read_text(encoding="utf-8")
    assert "isDevErrorDetails" in source
    assert "safeErrorDetails" in source
    assert "error.stack || error.message" not in source


def test_screen_guard_and_global_guards_use_safe_fields() -> None:
    guard = (FRONTEND / "components" / "withScreenGuard.tsx").read_text(encoding="utf-8")
    global_guards = (FRONTEND / "utils" / "globalGuards.ts").read_text(encoding="utf-8")
    assert "crashTelemetryFields" in guard
    assert "crashTelemetryFields" in global_guards
    assert "error.message," not in guard
    assert "error?.message ?? error" not in global_guards
