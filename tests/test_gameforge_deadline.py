import pytest
from skeleton.frontier.gameforge_deadline import Deadline

def test_deadline_never_goes_negative():
 d=Deadline(5); assert d.spend(2); assert not d.spend(4); assert d.remaining==0

def test_deadline_rejects_negative_cost():
 with pytest.raises(ValueError): Deadline(1).spend(-1)
