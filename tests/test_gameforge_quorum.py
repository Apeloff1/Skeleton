import pytest
from skeleton.frontier.gameforge_quorum import quorum,reached

def test_majority_quorum():
    assert [quorum(n) for n in (1,2,3,4,5)]==[1,2,2,3,3]
    assert reached(5,3); assert not reached(5,2)

def test_quorum_rejects_invalid_values():
    with pytest.raises(ValueError): quorum(0)
    with pytest.raises(ValueError): reached(3,4)
