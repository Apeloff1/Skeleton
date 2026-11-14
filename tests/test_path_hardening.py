"""Adversarial coverage for path preflight and exact-host URL admission."""
import pytest

from backend.core.path_hardening import (
    audit_receipt,
    safe_join,
    validate_safe_identifier,
    validate_url_host,
)


@pytest.mark.parametrize("name", ["../etc/passwd", "/absolute", "..", "CON", "nul.txt", "a.", "a/b", "a\\b", "x" * 129])
def test_identifier_rejects_nonportable_names(name):
    with pytest.raises(ValueError):
        validate_safe_identifier(name)


def test_identifier_accepts_portable_name():
    assert validate_safe_identifier("safe_shard_01") == "safe_shard_01"


@pytest.mark.parametrize("part", ["..", ".", "/absolute", "C:\\absolute", "a\\b", "a/b", "a:b", "NUL.txt", "trailing.", "trailing ", "x\x00y", ""])
def test_join_rejects_ambiguous_components(tmp_path, part):
    with pytest.raises(ValueError):
        safe_join(tmp_path, part)


def test_join_contains_existing_root(tmp_path):
    assert safe_join(tmp_path, "sub", "file.zst") == tmp_path.resolve() / "sub" / "file.zst"


def test_join_requires_existing_root(tmp_path):
    with pytest.raises(ValueError):
        safe_join(tmp_path / "missing", "file")


def test_join_rejects_symlink_even_if_target_is_inside_root(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("platform does not permit creating symlinks")
    with pytest.raises(ValueError):
        safe_join(tmp_path, "link", "file")
    with pytest.raises(ValueError):
        safe_join(link, "file")


@pytest.mark.parametrize("url", [
    "ftp://example.com/path", "http://example.com/path", "//example.com/path",
    "https://evil-example.com", "https://example.com.evil.net", "https://sub.example.com",
    "https://user@example.com", "https://example.com:0", "https://example.com:65536",
    "https://example.com:", "https://example.com.", "https://example.com\\@evil.test",
    "https://[::1]junk:8080", "https://example.com:0443",
    "https://exa%6dple.com", " https://example.com", "https://example.com/\n",
])
def test_url_rejects_ambiguous_or_unadmitted_authorities(url):
    with pytest.raises(ValueError):
        validate_url_host(url)


def test_url_allowlist_is_exact_and_empty_is_deny_all():
    assert validate_url_host("https://example.com/path") == "https://example.com/path"
    assert validate_url_host("http://127.0.0.1:8080") == "http://127.0.0.1:8080"
    assert validate_url_host("https://sub.example.com", {"sub.example.com"})
    assert validate_url_host("http://[::1]:8080", {"::1"})
    with pytest.raises(ValueError):
        validate_url_host("https://example.com", set())


def test_audit_receipt_is_bound_to_action_and_path(tmp_path):
    p = tmp_path / "file"
    receipt = audit_receipt(p, "read")
    assert receipt["stored_prose"] == 0
    assert len(receipt["sha256"]) == 64
    assert receipt == audit_receipt(p, "read")
    assert receipt["sha256"] != audit_receipt(p, "write")["sha256"]
    assert receipt["sha256"] != audit_receipt(p.with_name("other"), "read")["sha256"]
