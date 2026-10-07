import pytest
from skeleton.runtime.model_eviction import *
def test_pinned_and_inflight_models_never_evict():
 for s in (DrainState(0,True),DrainState(1,False)):
  with pytest.raises(PermissionError):evict("m",s,EvictionPolicy(10),20)
def test_eviction_is_reloadable_and_thrash_guarded():
 assert evict("m",DrainState(0,False),EvictionPolicy(10),20).reloadable
 with pytest.raises(PermissionError):evict("m",DrainState(0,False),EvictionPolicy(10),1)

def test_negative_inflight_and_idle_rejected():
 import pytest
 with pytest.raises(ValueError):DrainState(-1,False)
 with pytest.raises(ValueError):evict("m",DrainState(0,False),EvictionPolicy(1),-1)
