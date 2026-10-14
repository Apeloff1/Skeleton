from skeleton.retrieval.provenance import ProvenanceLedger
def test_record_idempotency_key_replays_original_entry():
 l=ProvenanceLedger()
 a=l.record("s","op","in","out",metadata={"x":1},idempotency_key="k")
 b=l.record("s","op","in","out",metadata={"x":1},idempotency_key="k")
 assert a is b and l.stats()["recorded"]==1
def test_record_idempotency_key_rejects_payload_change():
 l=ProvenanceLedger();l.record("s","op","in","out",idempotency_key="k")
 try:l.record("s","op","in","changed",idempotency_key="k")
 except ValueError as exc:assert "different" in str(exc)
 else:raise AssertionError("conflicting idempotency key accepted")
def test_legacy_record_without_key_still_records_each_call():
 l=ProvenanceLedger();a=l.record("s","op","in","out");b=l.record("s","op","in","out")
 assert a.entry_id!=b.entry_id and l.stats()["recorded"]==2

def test_snapshot_restores_idempotency_binding():
 l=ProvenanceLedger();a=l.record("s","op","in","out",metadata={"x":1},idempotency_key="k")
 restored=ProvenanceLedger.from_snapshot(l.snapshot())
 b=restored.record("s","op","in","out",metadata={"x":1},idempotency_key="k")
 assert b.entry_id==a.entry_id and restored.stats()["recorded"]==1
def test_snapshot_tampering_fails_closed():
 l=ProvenanceLedger();l.record("s","op","in","out",idempotency_key="k")
 snap=l.snapshot();snap["entries"][0]["operation"]="changed"
 try:ProvenanceLedger.from_snapshot(snap)
 except ValueError as exc:assert "digest" in str(exc)
 else:raise AssertionError("tampered snapshot accepted")
def test_snapshot_rejects_missing_parent_even_with_valid_digest():
 import hashlib,json
 l=ProvenanceLedger();snap=l.snapshot()
 snap["entries"]=[{"entry_id":"child","source":"s","operation":"op","input_hash":"i","output_hash":"o","timestamp":1.0,"metadata":{},"parent_id":"missing"}]
 snap["stats"]={"recorded":1,"queries":0}
 body={k:v for k,v in snap.items() if k!="digest"}
 snap["digest"]=hashlib.blake2b(json.dumps(body,sort_keys=True,separators=(",",":")).encode(),digest_size=16).hexdigest()
 try:ProvenanceLedger.from_snapshot(snap)
 except ValueError as exc:assert "parent" in str(exc)
 else:raise AssertionError("missing parent accepted")
