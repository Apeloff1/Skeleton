import tempfile
from skeleton.ai.webcrawler.storage import SqliteCrawlStore
from skeleton.ai.webcrawler.durable_frontier import DurableFrontier
def test_claim_is_atomic_and_exclusive():
 with tempfile.TemporaryDirectory() as d:
  s=SqliteCrawlStore(d+"/c.db");q=DurableFrontier(s.db);q.enqueue("https://a.example/x")
  a=q.claim("a",now=0,ttl=10);assert a
  assert q.claim("b",now=0,ttl=10) is None
  assert q.complete(a) and q.size()==0
def test_expired_claim_can_be_reclaimed_and_stale_owner_is_fenced():
 with tempfile.TemporaryDirectory() as d:
  s=SqliteCrawlStore(d+"/c.db");q=DurableFrontier(s.db);q.enqueue("https://a.example/x")
  old=q.claim("a",now=0,ttl=1);new=q.claim("b",now=2,ttl=10)
  assert new and old.token!=new.token
  assert not q.complete(old);assert q.complete(new)
def test_retry_atomically_releases_claim_with_new_schedule():
 with tempfile.TemporaryDirectory() as d:
  s=SqliteCrawlStore(d+"/c.db");q=DurableFrontier(s.db);q.enqueue("https://a.example/x")
  a=q.claim("a",now=0,ttl=10);assert q.retry(a,ready_at=20,attempts=1)
  assert q.claim("b",now=19,ttl=10) is None
  b=q.claim("b",now=20,ttl=10);assert b and b.attempts==1
