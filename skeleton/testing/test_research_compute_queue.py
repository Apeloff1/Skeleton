from skeleton.runtime.research_queue import *
def test_research_never_consumes_production_reservation():
 q=ResearchQueue((ResearchComputeJob("r",10,100,"p"),));assert q.allocate(10,8)==(ResearchAllocation("r",2),)
def test_priority_is_deterministic():assert ResearchQueue((ResearchComputeJob("b",1,1,"p"),ResearchComputeJob("a",2,1,"p"))).allocate(1,0)[0].job_id=="a"

def test_production_reservation_cannot_exceed_capacity():
 import pytest
 with pytest.raises(ValueError):ResearchQueue(()).allocate(1,2)
