"""Owner-bound Dragon crawler playback: no cross-account event disclosure."""
import sqlite3
import pytest
from skeleton.ai.webcrawler.dragon_session_projection import DragonSessionProjection


def test_crawl_attaches_only_trusted_owner_and_replays_real_events():
    db=sqlite3.connect(":memory:")
    bridge=DragonSessionProjection(db)
    with pytest.raises(PermissionError):
        bridge.attach("owner-a","session-1",authorized=False,at=1)
    bridge.attach("owner-a","session-1",authorized=True,at=1)
    first=bridge.journal.append("session-1","frontier_discovered",
                                "https://example.org/a",at=1.5,
                                payload={"depth":0})
    second=bridge.journal.append("session-1","dragon_travel",
                                 "https://example.org/a",at=2)
    read=bridge.read("owner-a",authorized=True,after_sequence=0,limit=1)
    assert read.active and read.session_id=="session-1"
    assert read.events[0]["event_id"]==first.event_id
    assert read.has_more and read.next_cursor=="1"
    more=bridge.read("owner-a",authorized=True,after_sequence=1,limit=20)
    assert [e["event_id"] for e in more.events]==[second.event_id]
    assert not more.has_more
    assert not bridge.read("owner-b",authorized=True).active
    with pytest.raises(PermissionError):
        bridge.attach("owner-b","session-1",authorized=True,at=2)
    with pytest.raises(PermissionError):
        bridge.read("owner-a",authorized=False)
    assert bridge.close("owner-a","session-1",authorized=True)
    assert bridge.read("owner-a",authorized=True).events==()


def test_corrupt_crawl_chain_fails_closed():
    db=sqlite3.connect(":memory:")
    bridge=DragonSessionProjection(db)
    bridge.attach("owner-a","session-1",authorized=True,at=1)
    bridge.journal.append("session-1","fetch_started","https://example.org",at=2)
    db.execute("""UPDATE dragon_companion_events SET kind='crawl_complete'
                  WHERE session_id='session-1'""")
    db.commit()
    with pytest.raises(ValueError,match="integrity"):
        bridge.read("owner-a",authorized=True)
