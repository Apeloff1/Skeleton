import tempfile
from skeleton.ai.webcrawler.storage import SqliteCrawlStore
from skeleton.ai.webcrawler.outbox import IngestionOutbox
def test_plan_is_deterministic_and_survives_restart():
 with tempfile.TemporaryDirectory() as d:
  p=d+"/c.db";s=SqliteCrawlStore(p);o=IngestionOutbox(s.db)
  a=o.plan("k",[{"chunk_id":"a","text":"x"},{"chunk_id":"b","text":"y"}]);s.close()
  s=SqliteCrawlStore(p);b=IngestionOutbox(s.db).plan("k",[{"chunk_id":"a","text":"x"},{"chunk_id":"b","text":"y"}])
  assert [x.operation_id for x in a]==[x.operation_id for x in b]
def test_changed_plan_for_same_ordinal_fails_closed():
 with tempfile.TemporaryDirectory() as d:
  s=SqliteCrawlStore(d+"/c.db");o=IngestionOutbox(s.db);o.plan("k",[{"text":"x"}])
  try:o.plan("k",[{"text":"changed"}])
  except ValueError:pass
  else:raise AssertionError("changed persisted plan accepted")
def test_completed_operation_result_replays():
 with tempfile.TemporaryDirectory() as d:
  s=SqliteCrawlStore(d+"/c.db");o=IngestionOutbox(s.db);op=o.plan("k",[{"text":"x"}])[0]
  o.complete(op.operation_id,{"entry_id":"p1"})
  row=o.pending("k")[0];assert row.state=="complete" and row.result=={"entry_id":"p1"}
