import pytest

from skeleton.build.delivery._util import DeliveryError
from skeleton.build.delivery.secrets_guard import assert_clean, is_secret_ref, scan_mapping, scan_text, shannon_entropy


def test_secret_refs_are_allowed():
    assert is_secret_ref("secret://skeleton/db-url")
    assert scan_mapping({"db": {"password": "secret://db/pw"}}) == ()


@pytest.mark.parametrize(
    "value,rule",
    [
        # Assemble synthetic secret-shaped inputs at runtime; never commit literal credentials.
        ("AKIA" + "A" * 16, "aws-access-key"),
        ("ghp_" + "a" * 36, "github-token"),
        ("".join(("-----BEGIN ", "RSA ", "PRIVATE KEY-----")), "private-key"),
        ("".join(("postgres://", "user:", "pw@", "host/db")), "url-credentials"),
    ],
)
def test_detects_known_patterns(value, rule):
    rules = {f.rule for f in scan_mapping({"x": value})}
    assert rule in rules


def test_sensitive_key_literal_and_entropy():
    assert {f.rule for f in scan_mapping({"api_key": "hunter2"})} == {"sensitive-key-literal"}
    assert "high-entropy" in {f.rule for f in scan_mapping({"blob": "q8Zr2LmX9vKp4TbN7wYc1HsD6fGj3eRu"})}
    assert shannon_entropy("aaaa") == 0


def test_scan_text_and_assert_clean():
    findings = scan_text("cfg.env", "ok=1\nTOKEN=ghp_" + "b" * 40 + "\n")
    assert findings and findings[0].location == "cfg.env:2"
    with pytest.raises(DeliveryError):
        assert_clean(findings)
    assert_clean(())
