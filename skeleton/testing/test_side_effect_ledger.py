import pytest
from skeleton.persistence.side_effect_ledger import *
def e():return SideEffect("e","charge","key")
def test_unknown_outcome_blocks_duplicate_retry():
 a=begin(e());u=EffectAttempt(a.effect,a.attempt,"unknown")
 with pytest.raises(PermissionError):begin(e(),(u,))
def test_outcome_can_remain_unknown():assert receipt(begin(e()),"unknown").outcome=="unknown"

def test_receipt_transitions_attempt_state():assert receipt(begin(SideEffect("e","op","k")),"succeeded").attempt.state=="succeeded"
def test_retry_number_is_scoped_to_idempotency_key():
 a=EffectAttempt(SideEffect("e","op","k"),3,"failed");assert begin(SideEffect("e2","op","k"),(a,)).attempt==4
