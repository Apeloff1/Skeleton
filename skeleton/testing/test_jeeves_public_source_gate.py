"""Market citations must not launder loopback/private endpoints as public data."""
from __future__ import annotations

import pytest

from skeleton.developer.jeeves_game_quality import QualityError, _source


def citation(url: str) -> dict[str, str]:
    return {
        "url": url,
        "issuer": "Synthetic publisher",
        "kind": "publisher_filing",
        "published": "2026-07-01",
    }


@pytest.mark.parametrize("url", [
    "https://127.0.0.1/secret",
    "https://192.168.1.10/private",
    "https://10.0.0.1/",
    "https://169.254.169.254/latest/meta-data/",
    "https://[::1]/",
    "https://[fd00::1]/",
    "https://localhost/",
    "https://localhost.localdomain/",
    "https://metadata.google.internal/",
    "https://host.docker.internal/",
    "https://workstation.local/",
    "https://intranet.lan/",
    "https://private.home.arpa/",
    "https://company.onion/",
    "https://anything.invalid/",
    "https://bad.example/",
    "https://publisher.test/",
    "https://publisher.example.com./",
    "https://127.0.0.1.evil.local/",
    "https://singlelabel/",
    "https://2130706433/",
    "https://publisher.example.com:0/",
    "https://publisher.example.com:65536/",
    "https://user:pass@publisher.example.com/",
    "http://publisher.example.com/",
])
def test_local_private_ambiguous_and_untrusted_sources_rejected(url):
    with pytest.raises(QualityError):
        _source(citation(url), "sales")


@pytest.mark.parametrize("url", [
    "https://publisher.example.com/ir/2026",
    "https://reviews.example.org/critics/2019",
    "https://public-docs.gov/filings?id=2",
    "https://research.example.net:8443/reports",
])
def test_well_formed_public_domain_citations_retain_compatibility(url):
    got = _source(citation(url), "sales")
    assert got["url"] == url
    assert got["published"] == "2026-07-01"


def test_citation_format_is_not_independent_verification():
    out = _source(citation("https://publisher.example.com/report"), "sales")
    assert out["issuer"] == "Synthetic publisher"
    # Validation only checks operator-supplied metadata; it makes no request.
    assert "verified" not in out
