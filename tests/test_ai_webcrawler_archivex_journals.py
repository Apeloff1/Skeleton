"""Offline journal ingestion tests for ArchiveX."""
import sqlite3
import pytest

from skeleton.ai.webcrawler.archivex import ArchiveX
from skeleton.ai.webcrawler.archivex_journals import ingest_open_access_journal


XML = b"""<article xmlns:xlink="http://www.w3.org/1999/xlink"><front><article-meta><permissions><license xlink:href="https://creativecommons.org/licenses/by/4.0/"/></permissions><title-group>
<article-title>Evidence review</article-title>
</title-group></article-meta></front><body>
<sec><title>Methods</title><p>Reproducible method A.</p></sec>
<sec><title>Results</title><p>Observed result B.</p></sec>
</body><back><ref-list><ref id="ref-1"/><ref id="ref-2"/></ref-list></back>
</article>"""


def archive():
    return ArchiveX(sqlite3.connect(":memory:"))


def ingest(store, xml=XML, **kwargs):
    return ingest_open_access_journal(
        store, owner="alice", pmcid="PMC123456",
        fetch_xml=lambda url: xml, observed_at=100, now=100,
        license_id="CC-BY-4.0", authorized=True, **kwargs,
    )


def test_article_sections_references_and_snapshot():
    store = archive()
    receipt = ingest(store)
    assert receipt.title == "Evidence review"
    assert len(receipt.sections) == 2
    assert receipt.sections[0].heading == "Methods"
    assert receipt.reference_ids == ("ref-1", "ref-2")
    assert store.read("alice", receipt.snapshot.snapshot_id,
                      authorized=True)[1] == XML


def test_repeated_ingestion_is_deterministic():
    store = archive()
    assert ingest(store) == ingest(store)


def test_unapproved_license_fails_before_fetch():
    called = []
    with pytest.raises(PermissionError):
        ingest_open_access_journal(
            archive(), owner="alice", pmcid="PMC123456",
            fetch_xml=lambda url: called.append(url),
            observed_at=100, now=100, license_id="unknown",
            authorized=True,
        )
    assert not called


def test_explicit_consent_required():
    with pytest.raises(PermissionError):
        ingest_open_access_journal(
            archive(), owner="alice", pmcid="PMC123456",
            fetch_xml=lambda url: XML, observed_at=100, now=100,
            license_id="CC-BY-4.0", authorized=False,
        )


def test_xml_entities_rejected():
    malicious = b'<!DOCTYPE article [<!ENTITY x "EXPAND">]><article>&x;</article>'
    with pytest.raises(ValueError, match="entity"):
        ingest(archive(), malicious)


def test_malformed_xml_rejected_without_archival_side_effect():
    store = archive()
    with pytest.raises(ValueError, match="XML"):
        ingest(store, b"<article>")
    assert store.timeline(
        "alice",
        "https://www.ebi.ac.uk/europepmc/webservices/rest/PMC123456/fullTextXML",
        authorized=True,
    ) == ()


def test_pmc_identifier_validation():
    with pytest.raises(ValueError, match="PMC"):
        ingest_open_access_journal(
            archive(), owner="alice", pmcid="../../secret",
            fetch_xml=lambda url: XML, observed_at=100, now=100,
            license_id="CC-BY-4.0", authorized=True,
        )

def test_missing_article_license_fails_closed():
    store = archive()
    without = XML.replace(b"<permissions>", b"<ignored>").replace(b"</permissions>", b"</ignored>")
    without = without.replace(b"<license xlink:href=", b"<other xlink:href=")
    with pytest.raises(PermissionError, match="license"):
        ingest(store, without)
    assert store.db.execute("SELECT COUNT(*) FROM archivex_snapshots").fetchone()[0] == 0


def test_spoofed_article_license_fails_closed():
    store = archive()
    restricted = XML.replace(
        b"https://creativecommons.org/licenses/by/4.0/",
        b"https://publisher.example.org/all-rights-reserved",
    )
    with pytest.raises(PermissionError, match="license"):
        ingest(store, restricted)
    assert store.db.execute("SELECT COUNT(*) FROM archivex_snapshots").fetchone()[0] == 0


def test_mismatched_license_fails_closed():
    store = archive()
    cc0 = XML.replace(
        b"https://creativecommons.org/licenses/by/4.0/",
        b"https://creativecommons.org/publicdomain/zero/1.0/",
    )
    with pytest.raises(PermissionError, match="disagrees"):
        ingest(store, cc0)
