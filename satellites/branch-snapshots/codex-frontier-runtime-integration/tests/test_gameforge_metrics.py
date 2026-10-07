import pytest
from skeleton.frontier.gameforge_metrics import CounterSet

def test_counter_snapshot_isolated():
    c=CounterSet(("ok","shed")); c.inc("ok",2); s=c.snapshot(); s["ok"]=99; assert c.snapshot()["ok"]==2

def test_counter_rejects_unknown_and_negative():
    c=CounterSet(("ok",))
    with pytest.raises(KeyError): c.inc("nope")
    with pytest.raises(ValueError): c.inc("ok",-1)
