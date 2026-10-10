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
