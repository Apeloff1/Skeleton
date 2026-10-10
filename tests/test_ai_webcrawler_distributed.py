import tempfile
from skeleton.ai.webcrawler.leases import SqliteLeaseStore
from skeleton.ai.webcrawler.traps import TrapGuard
from skeleton.ai.webcrawler.storage import SqliteCrawlStore
from skeleton.ai.webcrawler.migrations import SCHEMA_VERSION

def test_lease_excludes_second_worker_until_expiry():
    with tempfile.TemporaryDirectory() as d:
        s=SqliteLeaseStore(d+"/l.db")
        a=s.acquire("item","worker-a",now=0,ttl=10)
        assert a and s.acquire("item","worker-b",now=5,ttl=10) is None
        b=s.acquire("item","worker-b",now=11,ttl=10)
        assert b and b.owner=="worker-b"
        assert not s.release(a)
        assert s.release(b)

def test_lease_token_fences_stale_owner_after_reacquire():
    with tempfile.TemporaryDirectory() as d:
        s=SqliteLeaseStore(d+"/l.db")
        a=s.acquire("item","worker-a",now=0,ttl=1)
        b=s.acquire("item","worker-a",now=2,ttl=10)
        assert a.token != b.token
        assert s.renew(a,now=2,ttl=10) is None

def test_trap_guard_rejects_common_infinite_spaces():
    g=TrapGuard()
    assert not g.inspect("https://example.com/x?sessionid=abc").allowed
    assert not g.inspect("https://example.com/2026/10/07?next=1").allowed
    assert not g.inspect("https://example.com/"+"/".join(["x"]*21)).allowed
    assert g.inspect("https://example.com/articles/research?q=ai").allowed

def test_store_records_latest_schema_version():
    with tempfile.TemporaryDirectory() as d:
        s=SqliteCrawlStore(d+"/c.db")
        assert s.db.execute("SELECT version FROM schema_version").fetchone()[0] == SCHEMA_VERSION
        assert s.db.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_documents_fetched_at'").fetchone()
        s.close()
