import pytest
from skeleton.frontier.gameforge_scheduler import Scheduler

def test_scheduler_cycles_workers():
 s=Scheduler({"a":1,"b":2}); assert [s.next() for _ in range(4)]==["a","b","a","b"]

def test_scheduler_requires_positive_weights():
 with pytest.raises(ValueError): Scheduler({"a":0})
