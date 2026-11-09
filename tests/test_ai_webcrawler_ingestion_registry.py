import tempfile
from skeleton.ai.webcrawler.storage import SqliteCrawlStore
from skeleton.ai.webcrawler.ingestion_registry import DurableIngestionRegistry,IngestionLease
def test_completed_receipt_replays_after_registry_restart():
 with tempfile.TemporaryDirectory() as d:
  p=d+"/c.db";s=SqliteCrawlStore(p);r=DurableIngestionRegistry(s.db)
  lease=r.reserve("k","a",now=0,ttl=10);assert isinstance(lease,IngestionLease)
  assert r.complete(lease,{"chunks":3});s.close()
  s=SqliteCrawlStore(p);r=DurableIngestionRegistry(s.db)
  assert r.reserve("k","b",now=100,ttl=10)=={"chunks":3}
def test_live_reservation_excludes_second_worker():
 with tempfile.TemporaryDirectory() as d:
  s=SqliteCrawlStore(d+"/c.db");r=DurableIngestionRegistry(s.db)
  assert r.reserve("k","a",now=0,ttl=10)
  assert r.reserve("k","b",now=1,ttl=10) is None
def test_expired_reservation_is_fenced_after_takeover():
 with tempfile.TemporaryDirectory() as d:
  s=SqliteCrawlStore(d+"/c.db");r=DurableIngestionRegistry(s.db)
  old=r.reserve("k","a",now=0,ttl=1);new=r.reserve("k","b",now=2,ttl=10)
  assert isinstance(new,IngestionLease) and new.token!=old.token
  assert not r.complete(old,{"bad":1})
  assert r.complete(new,{"ok":1})
def test_abandon_allows_immediate_retry():
 with tempfile.TemporaryDirectory() as d:
  s=SqliteCrawlStore(d+"/c.db");r=DurableIngestionRegistry(s.db)
  a=r.reserve("k","a",now=0,ttl=10);assert r.abandon(a)
  assert r.reserve("k","b",now=0,ttl=10)
