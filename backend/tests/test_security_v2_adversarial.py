"""Regression tests for security-v2 input and logging boundaries."""
from __future__ import annotations

import logging

from core.security_v2 import SecretsScrubFilter
from middleware.request_id import normalize_request_id


def test_request_id_accepts_small_log_safe_identifier():
    assert normalize_request_id("client.trace-42:retry_1") == "client.trace-42:retry_1"


def test_request_id_rejects_log_injection_and_oversized_values():
    injected = normalize_request_id("trusted\nlevel=CRITICAL forged=true")
    oversized = normalize_request_id("a" * 65)

    assert "\n" not in injected
    assert injected != "trusted\nlevel=CRITICAL forged=true"
    assert len(injected) == 16
    assert oversized != "a" * 65
    assert len(oversized) == 16


def test_secret_scrubber_covers_modern_provider_and_generic_credentials():
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=(
            "openai=sk-proj-abcdefghijklmnopqrstuvwxyz0123456789 "
            "password=hunter2-secret "
            "Authorization: Bearer abcdefghijklmnopqrstuvwxyz012345"
        ),
        args=(),
        exc_info=None,
    )

    assert SecretsScrubFilter().filter(record)
    rendered = record.getMessage()
    assert "sk-proj-abcdefghijklmnopqrstuvwxyz0123456789" not in rendered
    assert "hunter2-secret" not in rendered
    assert "abcdefghijklmnopqrstuvwxyz012345" not in rendered
    assert "sk-***" in rendered
    assert "password=***" in rendered
    assert "Bearer ***" in rendered
