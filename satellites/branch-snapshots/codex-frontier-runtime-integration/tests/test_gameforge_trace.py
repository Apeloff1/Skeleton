from skeleton.frontier.gameforge_trace import TraceRecord

def test_trace_record_key_is_deterministic():
    record = TraceRecord("req-1", "accept", 7)
    assert record.key() == ("req-1", 7)
    assert record == TraceRecord("req-1", "accept", 7)
