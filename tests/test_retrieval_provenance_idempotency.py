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
