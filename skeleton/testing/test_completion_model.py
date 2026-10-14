from __future__ import annotations
import hashlib,pytest
from skeleton.automation.completion_model import *
S=lambda x:hashlib.sha256(x.encode()).hexdigest()
def done(i="ACC.1",source=1,sign=1):return AtomicCompletion(i,CompletionState.COMPLETE,S(i),True,sign,source)
def test_complete_requires_signed_fresh_evidence():
 with pytest.raises(CompletionError,match="signed evidence"):AtomicCompletion("ACC.1",CompletionState.COMPLETE)
 with pytest.raises(CompletionError,match="stale signoff"):done(source=2,sign=1)
def test_blocker_is_non_compensable_even_when_all_records_complete():
 r=rollup((done("ACC.1"),done("ACC.2")),(CompletionBlocker("ACC.2","critical regression"),))
 assert r.state is CompletionState.BLOCKED and r.percent==100
def test_partial_is_derived_not_manually_supplied():
 r=rollup((done(),AtomicCompletion("ACC.2",CompletionState.PENDING)))
 assert r.state is CompletionState.PARTIAL and r.percent==50
def test_duplicate_accountability_cannot_double_count_progress():
 with pytest.raises(CompletionError,match="duplicate accountability"):rollup((done(),done()))
def test_record_blocked_state_surfaces_without_external_blocker():
 r=rollup((done(),AtomicCompletion("ACC.2",CompletionState.BLOCKED)))
 assert r.state is CompletionState.BLOCKED and r.blocked_ids==("ACC.2",)
def test_noncomplete_record_cannot_smuggle_signoff():
 with pytest.raises(CompletionError,match="cannot carry"):AtomicCompletion("ACC.1",CompletionState.PARTIAL,S("x"),True,1,1)
