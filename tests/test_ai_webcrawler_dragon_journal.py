import sqlite3
import pytest
from skeleton.ai.webcrawler.dragon_journal import DragonEventJournal

def test_journal_persists_replays_and_verifies(tmp_path):
    path=tmp_path/"dragon.sqlite"
    db=sqlite3.connect(path)
    journal=DragonEventJournal(db)
    first=journal.append("session","acquisition_accepted","https://example.org",at=1,payload={"content_hash":"abc"})
    second=journal.append("session","burn_started","https://example.org",at=2)
    assert first.sequence==1 and second.sequence==2
    assert journal.verify("session")
    page=journal.page("session",limit=1)
    assert page["hasMore"] and page["nextCursor"]=="1"
    following=journal.page("session",after=1)
    assert following["events"][0]["kind"]=="burn_started"
    db.close()
    reopened=DragonEventJournal(sqlite3.connect(path))
    assert reopened.verify("session")
    assert len(reopened.page("session")["events"])==2

def test_journal_detects_tampering_and_rejects_invalid_payload():
    db=sqlite3.connect(":memory:")
    journal=DragonEventJournal(db)
    journal.append("s","fetch_started","https://example.org",at=1)
    db.execute("UPDATE dragon_companion_events SET kind='burn_complete'")
    assert not journal.verify("s")
    with pytest.raises(ValueError):
        journal.append("s","fetch_started","https://example.org",at=float("nan"))
    with pytest.raises(ValueError):
        journal.append("s","fetch_started","https://example.org",at=2,payload={"bad":float("nan")})

def test_sessions_are_isolated():
    journal=DragonEventJournal(sqlite3.connect(":memory:"))
    journal.append("alice","fetch_started","https://example.org/a",at=1)
    journal.append("bob","policy_rejected","https://example.org/b",at=1)
    assert [x["url"] for x in journal.page("alice")["events"]]==["https://example.org/a"]
    assert journal.verify("alice") and journal.verify("bob")


@pytest.mark.parametrize("url", [
    "https://", "http://", "https://user:secret@example.org/file",
    "https://example.org/#fragment", "https://example.org/\ncommand",
    "https://[invalid-host", "file:///local/secrets",
])
def test_journal_rejects_untrusted_event_origin(url):
    journal = DragonEventJournal(sqlite3.connect(":memory:"))
    with pytest.raises(ValueError, match="event URL"):
        journal.append("session", "fetch_started", url, at=1)


@pytest.mark.parametrize("bad_session", [
    "", "name with spaces", "../session", "session\ncontrol", "s" * 129,
])
def test_journal_requires_bounded_scoped_session_identifiers(bad_session):
    journal = DragonEventJournal(sqlite3.connect(":memory:"))
    with pytest.raises(ValueError, match="session"):
        journal.append(bad_session, "fetch_started", "https://example.org", at=1)


def test_journal_rejects_nonobject_and_exhaustive_json_payloads():
    journal = DragonEventJournal(sqlite3.connect(":memory:"))
    for payload in ([], "text", [1, 2], {"huge": list(range(5000))},
                    {"invalid": object()}, {"nonfinite": float("inf")}):
        with pytest.raises(ValueError):
            journal.append("session", "fetch_started", "https://example.org",
                           at=1, payload=payload)
    cycle = {}
    cycle["self"] = cycle
    with pytest.raises(ValueError, match="node/depth budget"):
        journal.append("session", "fetch_started", "https://example.org",
                       at=1, payload=cycle)


def test_verified_journal_page_provides_persistent_chain_receipts(tmp_path):
    path = tmp_path / "journal.sqlite"
    conn = sqlite3.connect(path)
    journal = DragonEventJournal(conn)
    a = journal.append("adventure", "fetch_started", "https://example.org", at=1)
    b = journal.append("adventure", "fetch_received", "https://example.org", at=2)
    page = journal.verified_page("adventure", limit=1)
    assert page["chain_verified"] is True
    assert page["hasMore"] is True
    assert page["chain_receipts"] == [{
        "sequence": 1, "previous_digest": "0" * 64, "digest": a.digest,
    }]
    page2 = journal.verified_page("adventure", after=1)
    assert page2["chain_receipts"] == [{
        "sequence": 2, "previous_digest": a.digest, "digest": b.digest,
    }]
    assert page2["events"][0]["kind"] == "fetch_received"
    conn.close()
    reopened = DragonEventJournal(sqlite3.connect(path))
    assert reopened.verified_page("adventure")["chain_verified"]


def test_corrupted_persisted_journal_fails_closed_without_exposing_verified_page():
    conn = sqlite3.connect(":memory:")
    journal = DragonEventJournal(conn)
    journal.append("s", "fetch_started", "https://example.org", at=1)
    conn.execute("UPDATE dragon_companion_events SET payload='not json'")
    assert journal.verify("s") is False
    with pytest.raises(ValueError, match="evidence chain"):
        journal.verified_page("s")


@pytest.mark.parametrize("kwargs", [
    {"after": True}, {"limit": False}, {"after": -1},
    {"limit": 0}, {"limit": 1001},
])
def test_verified_journal_paging_rejects_invalid_limits_and_cursors(kwargs):
    journal = DragonEventJournal(sqlite3.connect(":memory:"))
    with pytest.raises(ValueError, match="page parameters"):
        journal.verified_page("s", **kwargs)


def test_verified_journal_page_catches_modified_payload_between_check_and_return():
    from unittest.mock import patch
    journal = DragonEventJournal(sqlite3.connect(":memory:"))
    journal.append("s", "fetch_started", "https://example.org", at=1,
                   payload={"content_sha256": "a" * 64})
    original_page = journal.page

    def corrupted_page(*args, **kwargs):
        page = original_page(*args, **kwargs)
        page["events"][0]["payload"] = {"content_sha256": "b" * 64}
        return page

    assert journal.verify("s")
    with patch.object(journal, "page", side_effect=corrupted_page):
        with pytest.raises(ValueError, match="evidence digest mismatch"):
            journal.verified_page("s")


def test_verified_journal_page_rejects_swapped_receipt_after_chain_verification():
    from unittest.mock import patch
    journal = DragonEventJournal(sqlite3.connect(":memory:"))
    journal.append("s", "fetch_started", "https://example.org", at=1)
    real = journal.page

    def changed_identity(*args, **kwargs):
        p = real(*args, **kwargs)
        p["events"][0]["event_id"] = "f" * 64
        return p

    with patch.object(journal, "page", side_effect=changed_identity):
        with pytest.raises(ValueError, match="evidence changed"):
            journal.verified_page("s")
