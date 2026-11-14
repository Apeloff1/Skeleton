"""Adversarial tests for portable path and exact URL admission."""
from __future__ import annotations

import hashlib
import json

import pytest

from backend.core.path_hardening import (
    audit_receipt,
    safe_join,
    validate_safe_identifier,
    validate_url_host,
)


@pytest.mark.parametrize("name", [
    "../etc/passwd", "/absolute", "..", "file.", "CON.txt", "nul", "LPT9",
    "a:b", "x\\y", "a\n", "", "a" * 129,
])
def test_invalid_identifier(name):
    with pytest.raises(ValueError):
        validate_safe_identifier(name)


def test_portable_identifier():
    assert validate_safe_identifier("safe_shard_01") == "safe_shard_01"


def test_safe_join_contains_root(tmp_path):
    assert safe_join(tmp_path, "sub", "file.zst") == tmp_path / "sub" / "file.zst"


@pytest.mark.parametrize("part", ["..", "../escape", "/etc", "C:\\temp", "sub/file", "a\\b"])
def test_safe_join_denies_non_component_paths(tmp_path, part):
    with pytest.raises(ValueError):
        safe_join(tmp_path, part)


def test_existing_symlink_escape_denied(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (root / "escape").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable")
    with pytest.raises(ValueError):
        safe_join(root, "escape", "file")


@pytest.mark.parametrize("url", [
    "https://evil-example.com", "https://example.com.evil.net",
    "https://sub.example.com", "file://example.com/path",
    "ftp://example.com/path", "//example.com/path",
    "https://user:pass@example.com", "https://example.com@evil.net",
    "https://example.com:99999", "https://example.com:0",
    "https://example.com:", "https://example.com./",
    "https://example.com\\evil.net", "https://exa%6dple.com",
    "https://example.com\n", " https://example.com",
])
def test_url_admission_rejects_ambiguous_or_unlisted_authorities(url):
    with pytest.raises(ValueError):
        validate_url_host(url)


def test_url_exact_allowlist():
    assert validate_url_host("https://example.com/path") == "https://example.com/path"
    assert validate_url_host("https://sub.example.com", {"SUB.EXAMPLE.COM"})
    with pytest.raises(ValueError):
        validate_url_host("https://example.com", set())
    with pytest.raises(ValueError):
        validate_url_host("https://example.com", {"*.example.com"})


def test_audit_receipt_binds_resolved_path_and_action(tmp_path):
    p = tmp_path / "test"
    receipt = audit_receipt(p, "read")
    body = {"action": "read", "path": str(p.resolve())}
    assert receipt["stored_prose"] == 0
    assert receipt["sha256"] == hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert audit_receipt(p, "write")["sha256"] != receipt["sha256"]
    with pytest.raises(ValueError):
        audit_receipt(p, "bad:action")
