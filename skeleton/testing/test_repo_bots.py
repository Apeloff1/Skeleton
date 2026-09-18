import pytest

from skeleton.automation.free_model import redact_secrets
from skeleton.automation.repo_bots import extract_plan, safe_path


def test_safe_path_allows_repo_code_and_docs():
    assert safe_path("skeleton/foo.py")
    assert safe_path("tests/test_foo.py")
    assert safe_path("docs/REPO-BOTS.md")


def test_safe_path_rejects_control_plane_and_traversal():
    assert not safe_path(".github/workflows/evil.yml")
    assert not safe_path("deploy/prod.yaml")
    assert not safe_path("skeleton/../secrets.txt")
    assert not safe_path("/tmp/file.py")
    assert not safe_path("skeleton\\evil.py")


def test_extract_plan_rejects_untrusted_paths():
    with pytest.raises(ValueError):
        extract_plan('{"summary":"bad","files":[{"path":".github/workflows/x.yml","content":"x"}]}')


def test_redact_secrets_removes_common_credentials():
    text = "token=ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ123456 bearer Bearer abcdefghijklmnop123456"
    clean = redact_secrets(text)
    assert "ghp_" not in clean
    assert "Bearer abcdef" not in clean
