import pytest
from skeleton.storage.tiering import *

def test_move_preserves_integrity_and_redundancy():
    assert admit_move(TierMove("a","d",StorageTier("h",True,2),StorageTier("c",True,2),"m"),TieringPolicy(2)).digest == "d"

def test_unavailable_or_under_redundant_target_rejected():
    with pytest.raises(PermissionError):
        admit_move(TierMove("a","d",StorageTier("h",True,2),StorageTier("c",True,1),"m"),TieringPolicy(2))

def test_same_tier_move_and_invalid_redundancy_rejected():
    t=StorageTier("x",True,2)
    with pytest.raises(ValueError): admit_move(TierMove("a","d",t,t,"m"),TieringPolicy(1))
    with pytest.raises(ValueError): admit_move(TierMove("a","d",t,StorageTier("y",True,2),"m"),TieringPolicy(0))
