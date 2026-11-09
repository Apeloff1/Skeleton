import pytest
from skeleton.data.contracts import *
def c(unit="ms",cons=True):return DataContract("latency","v1",(DataField("x","latency",False,unit,"internal"),),60,(DataConsumer("api","v1"),) if cons else ())
def test_semantic_unit_change_is_breaking():assert require_migration(c(),c("s"))==("x",)
def test_breaking_change_requires_consumer_inventory():
 with pytest.raises(ValueError):require_migration(c(cons=False),c("s",False))

def test_duplicate_field_and_negative_freshness_rejected():
 import pytest
 f=DataField("x","m",False,"u","public")
 with pytest.raises(ValueError):DataContract("c","v",(f,f),1,())
 with pytest.raises(ValueError):DataContract("c","v",(f,),-1,())
