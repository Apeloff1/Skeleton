from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from zaibatsu import diplomat, gate


class _FakeApp:
    def __init__(self) -> None:
        self.middleware: list[type] = []

    def add_middleware(self, middleware_cls, **_kwargs) -> None:
        self.middleware.append(middleware_cls)


def test_declared_zaibatsu_modules_are_importable() -> None:
    package = importlib.import_module("zaibatsu")
    for module_name in package.__all__:
        # Some modules are intentionally lazy, but every advertised module must
        # exist and be importable from the canonical Python package.
        importlib.import_module(f"zaibatsu.{module_name}")


def test_gate_preserves_canonical_middleware_stack() -> None:
    app = _FakeApp()
    gate.install_middleware(app)
    assert app.middleware == [
        gate.AccessLogMiddleware,
        gate.RequestIdMiddleware,
        gate.RateLimiterMiddleware,
        gate.RoutePrivacyMiddleware,
    ]


def test_diplomat_resolves_explicit_library_without_loading(tmp_path: Path) -> None:
    # Explicit resolution is extension-agnostic: loading is deliberately a
    # separate step so discovery can be tested without a platform native build.
    library = tmp_path / "gf-ffi-test-library"
    library.write_bytes(b"not-a-real-library")
    assert diplomat.resolve_library_path(library) == library.resolve()


def test_diplomat_missing_default_is_nonfatal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GAMEFORGE_FFI_LIBRARY", raising=False)
    # Import and discovery are allowed in pure-Python deployments. If a local
    # native build happens to exist, discovery may return it; neither case may
    # raise just by probing availability.
    found = diplomat.resolve_library_path()
    assert found is None or found.is_file()


def test_open_default_fails_cleanly_when_resolution_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        diplomat,
        "resolve_library_path",
        lambda *_args, **_kwargs: None,
    )
    with pytest.raises(diplomat.NativeUnavailable, match="gf-ffi library not found"):
        diplomat.Zaibatsu.open_default()
