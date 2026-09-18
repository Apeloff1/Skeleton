from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "backend" / "server.py"


def _server_source() -> str:
    return SERVER.read_text(encoding="utf-8")


def test_header_bound_guard_is_registered_once_at_final_middleware_boundary() -> None:
    source = _server_source()
    marker = "app.add_middleware(HeaderBoundMiddleware)"
    assert source.count(marker) == 1
    guard = source.index(marker)

    for earlier in (
        "_install_api_middleware(app)",
        "app.add_middleware(SizeLimitMiddleware)",
        "app.add_middleware(AuditMiddleware, max_entries=5000)",
        "app.add_middleware(RateLimitMiddleware)",
        "app.add_middleware(RequestTimeoutMiddleware",
        "app.add_middleware(LoadSheddingMiddleware",
        "app.add_middleware(ObservabilityMiddleware)",
        "install_brotli(app)",
        "install_security_headers(",
        '@app.middleware("http")',
    ):
        assert source.index(earlier) < guard, earlier

    assert guard < source.index("# SOTA 2026 Feature Routes")


def test_header_bound_guard_uses_canonical_security_primitive() -> None:
    source = _server_source()
    assert (
        "from skeleton.api.request_bounds import HeaderBoundMiddleware"
        in source
    )
