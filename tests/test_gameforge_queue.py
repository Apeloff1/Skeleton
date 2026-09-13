import pytest
from skeleton.frontier.gameforge_queue import BoundedQueue

def test_queue_applies_backpressure():
 q=BoundedQueue(1); assert q.push("x"); assert not q.push("y"); assert q.pop()=="x"; assert q.push("y")

def test_queue_requires_capacity():
 with pytest.raises(ValueError): BoundedQueue(0)
