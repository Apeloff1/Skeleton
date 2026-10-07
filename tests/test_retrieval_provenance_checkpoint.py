from skeleton.retrieval.provenance import ProvenanceLedger
from skeleton.retrieval.provenance_checkpoint import ProvenanceCheckpoint
def test_checkpoint_round_trip_preserves_idempotency(tmp_path):
 p=ProvenanceCheckpoint(tmp_path/"ledger.json");l=ProvenanceLedger()
 a=l.record("s","op","in","out",idempotency_key="k");p.save(l)
 restored=p.load();b=restored.record("s","op","in","out",idempotency_key="k")
 assert a.entry_id==b.entry_id and restored.stats()["recorded"]==1
def test_missing_checkpoint_returns_empty_ledger(tmp_path):
 l=ProvenanceCheckpoint(tmp_path/"missing.json").load()
 assert l.stats()["entries"]==0
def test_corrupt_checkpoint_fails_closed(tmp_path):
 path=tmp_path/"ledger.json";path.write_text('{"version":1}',encoding="utf-8")
 try:ProvenanceCheckpoint(path).load()
 except ValueError:pass
 else:raise AssertionError("corrupt checkpoint accepted")
