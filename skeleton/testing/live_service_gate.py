"""Explicit custody for tests that contact disposable live/paid services.

This module does not grant network privileges. It protects legacy tests from
accidentally making live requests when imported by general pytest collection.
"""
from __future__ import annotations

import os
from urllib.parse import urlsplit


def approved_disposable_target() -> str:
    """Return a loopback-only explicit target after operator opt-in."""
    if os.environ.get("SKELETON_DISPOSABLE_E2E_APPROVED") != "1":
        raise ValueError("disposable live E2E requires explicit operator approval")
    candidate = os.environ.get("SKELETON_DISPOSABLE_E2E_URL", "").strip()
    if not candidate:
        raise ValueError("disposable live E2E target must be supplied explicitly")
    try:
        parsed = urlsplit(candidate)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("invalid disposable live E2E URL") from exc
    if (parsed.scheme not in {"http", "https"}
            or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in {"", "/"}
            or port is None or not 1 <= port <= 65535):
        raise ValueError("disposable live E2E must target a loopback URL with explicit port")
    return candidate.rstrip("/")


def require_destructive_build_approval() -> None:
    if os.environ.get("SKELETON_DESTRUCTIVE_E2E_APPROVED") != "1":
        raise ValueError("large live build requires separate destructive-operation approval")


def require_provider_job_approval() -> None:
    if os.environ.get("SKELETON_BILLED_E2E_APPROVED") != "1":
        raise ValueError("LLM-backed live E2E requires separate provider-budget approval")
