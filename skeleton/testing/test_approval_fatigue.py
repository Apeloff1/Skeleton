import pytest
from skeleton.security.approval_fatigue import *
S=lambda v="v1":ApprovalScope("u","write","repo",v)
def test_reuse_is_exact_scope_version_time_and_count_bounded():
 p=ApprovalReusePolicy(1,10);a=Approval(S(),0)
 assert a.reusable(S(),p,9)
 with pytest.raises(PermissionError):a.reuse(S("v2"),p,1)
 a=a.reuse(S(),p,1)
 with pytest.raises(PermissionError):a.reuse(S(),p,2)
 with pytest.raises(PermissionError):Approval(S(),0).reuse(S(),p,10)
def test_burden_tracks_fatigue_signals():
 b=burden(("requested","requested","reused","stale","overridden"));assert (b.requested,b.reused,b.stale,b.overridden)==(2,1,1,1)

def test_future_approval_cannot_be_reused():
 a=Approval(ApprovalScope("u","a","r","v"),10)
 assert not a.reusable(a.scope,ApprovalReusePolicy(1,10),9)
