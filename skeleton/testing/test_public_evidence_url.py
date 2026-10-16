"""Format-only source citation safety. No DNS/network calls are made."""
from __future__ import annotations

import pytest

from skeleton.security.public_evidence_url import (
    PublicEvidenceURLError,
    validate_public_evidence_url,
)


@pytest.mark.parametrize("url", [
    "https://www.eurogamer.net/reviews/2026",
    "https://www.metacritic.com/game/example-title",
    "https://8.8.8.8/status",
    "https://[2001:4860:4860::8888]/dns-query",
    "https://example.org:443/original?source=press",
])
def test_unambiguous_public_https_citations_are_accepted(url):
    assert validate_public_evidence_url(url) == url


@pytest.mark.parametrize("url", [
    "http://www.metacritic.com/reviews",
    "https://localhost:443/", "https://sub.localhost/",
    "https://localhost.localdomain/", "https://metadata.google.internal/",
    "https://foo.internal/", "https://myhost.local/",
    "https://private.test/", "https://hidden.onion/",
    "https://host.invalid/", "https://home.home.arpa/",
    "https://127.0.0.1/", "https://10.0.0.2/",
    "https://192.168.0.10/", "https://172.16.1.1/",
    "https://169.254.169.254/latest/meta-data",
    "https://[::1]/", "https://[fc00::2]/",
    "https://[fe80::1]/", "https://0.0.0.0/",
    "https://0177.0.0.1/", "https://2130706433/",
    "https://user:pass@example.org/",
    "https://example.org/#spoof", "https://example.org:444/",
    "https://example.org./", "https://example.org:443./",
    "https://example.org:bad/", "https://[::1%25lo0]/",
    "https://exämple.org/", "https://api.test/",
    "https://a..example.org/", "https://-bad.example.org/",
    "https://not valid.example.org/",
    "https://example.org\\@localhost/",
    " https://example.org/", "https://example.org/\n",
    "ftp://example.org", "not-a-url",
])
def test_local_private_reserved_or_ambiguous_evidence_is_rejected(url):
    with pytest.raises(PublicEvidenceURLError):
        validate_public_evidence_url(url)


@pytest.mark.parametrize("url", [None, 123, False, [], {}, "", "https://" + "a" * 1025])
def test_missing_or_invalid_evidence_type_refused(url):
    with pytest.raises(PublicEvidenceURLError):
        validate_public_evidence_url(url)
