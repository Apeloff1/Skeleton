import tempfile
from skeleton.ai.webcrawler.claiming import FrontierClaimer
from skeleton.ai.webcrawler.leases import SqliteLeaseStore

def test_two_workers_cannot_claim_same_url_concurrently():
    with tempfile.TemporaryDirectory() as d:
        store=SqliteLeaseStore(d+"/leases.db")
        a=FrontierClaimer(store,"worker-a",ttl=10)
        b=FrontierClaimer(store,"worker-b",ttl=10)
        work=a.claim("https://example.org/a",now=0)
        assert work
        assert b.claim("https://example.org/a",now=5) is None
        assert a.complete(work)
        assert b.claim("https://example.org/a",now=6)

def test_expired_worker_is_fenced_after_successor_claims():
    with tempfile.TemporaryDirectory() as d:
        store=SqliteLeaseStore(d+"/leases.db")
        a=FrontierClaimer(store,"worker-a",ttl=2)
        b=FrontierClaimer(store,"worker-b",ttl=10)
        stale=a.claim("https://example.org/a",now=0)
        current=b.claim("https://example.org/a",now=3)
        assert current
        assert a.renew(stale,now=3) is None
        assert not a.complete(stale)
        assert b.complete(current)
