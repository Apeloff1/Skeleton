"""Adversarial tests for path and URL hardening. Fail-closed."""
import pytest
from pathlib import Path
from backend.core.path_hardening import (
    validate_safe_identifier,
    safe_join,
    validate_url_host,
    audit_receipt,
)

def test_safe_identifier_rejects_path_injection():
    with pytest.raises(ValueError):
        validate_safe_identifier("../etc/passwd")
    with pytest.raises(ValueError):
        validate_safe_identifier("/absolute")
    with pytest.raises(ValueError):
        validate_safe_identifier("..")
    assert validate_safe_identifier("safe_shard_01") == "safe_shard_01"

def test_safe_join_contains_root():
    root = Path("/tmp/vault_test")
    root.mkdir(exist_ok=True)
    safe = safe_join(root, "sub", "file.zst")
    assert str(safe).startswith(str(root.resolve()))
    with pytest.raises(ValueError):
        safe_join(root, "..", "escape")

def test_url_host_allowlist():
    assert validate_url_host("https://example.com/path") 
    with pytest.raises(ValueError):
        validate_url_host("https://evil-example.com")
    with pytest.raises(ValueError):
        validate_url_host("https://example.com.evil.net")

def test_audit_receipt():
    p = Path("/tmp/test")
    rec = audit_receipt(p, "read")
    assert rec["stored_prose"] == 0
    assert "sha256" in rec
