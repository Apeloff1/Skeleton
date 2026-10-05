import pytest
from skeleton.runtime.gpu_memory import *
def test_reservation_precedes_load_and_is_deterministic():
 p,r=GPUMemoryPool(10).reserve("a",4);p,r2=p.reserve("b",3);assert (r.start,r2.start)==(0,4)
def test_oom_fails_before_allocation():
 with pytest.raises(MemoryError):GPUMemoryPool(2).reserve("x",3)

def test_duplicate_reservation_and_bool_size_rejected():
 import pytest
 p,r=GPUMemoryPool(10).reserve("r",2)
 with pytest.raises(ValueError):p.reserve("r",1)
 with pytest.raises(ValueError):p.reserve("x",True)
def test_release_reclaims_space():
 p,r=GPUMemoryPool(2).reserve("r",2);p=p.release("r");p,r2=p.reserve("x",2);assert r2.start==0
