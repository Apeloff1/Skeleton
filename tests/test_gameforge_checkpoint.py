import pytest
from skeleton.frontier.gameforge_checkpoint import Checkpoint

def test_checkpoint_only_advances():
    c=Checkpoint(); assert c.advance(2); assert not c.advance(2); assert not c.advance(1); assert c.sequence==2; assert c.advance(3)

def test_checkpoint_rejects_negative():
    with pytest.raises(ValueError): Checkpoint(-2)
    with pytest.raises(ValueError): Checkpoint().advance(-1)
