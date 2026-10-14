import sqlite3,tempfile
from skeleton.ai.webcrawler.storage import SqliteCrawlStore
from skeleton.ai.webcrawler.migrations import SCHEMA_VERSION
def test_fresh_store_records_current_schema_and_frontier():
 with tempfile.TemporaryDirectory() as d:
  s=SqliteCrawlStore(d+"/c.db")
  assert s.db.execute("SELECT version FROM schema_version").fetchone()[0]==SCHEMA_VERSION
  assert s.db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='durable_frontier'").fetchone()
  s.close()
def test_future_schema_fails_closed():
 with tempfile.TemporaryDirectory() as d:
  p=d+"/c.db";s=SqliteCrawlStore(p);s.db.execute("UPDATE schema_version SET version=?",(SCHEMA_VERSION+1,));s.db.commit();s.close()
  try:SqliteCrawlStore(p)
  except ValueError:pass
  else:raise AssertionError("future schema accepted")
def test_busy_timeout_is_configured_for_shared_workers():
 with tempfile.TemporaryDirectory() as d:
  s=SqliteCrawlStore(d+"/c.db")
  assert s.db.execute("PRAGMA busy_timeout").fetchone()[0]>=30000
  s.close()
