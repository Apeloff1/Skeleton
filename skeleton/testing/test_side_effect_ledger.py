import pytest
from skeleton.persistence.side_effect_ledger import *
def e():return SideEffect("e","charge","key")
def test_unknown_outcome_blocks_duplicate_retry():
 a=begin(e());u=EffectAttempt(a.effect,a.attempt,"unknown")
 with pytest.raises(PermissionError):begin(e(),(u,))
def test_outcome_can_remain_unknown():assert receipt(begin(e()),"unknown").outcome=="unknown"
