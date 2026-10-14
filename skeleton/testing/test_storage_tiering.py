import pytest
from skeleton.storage.tiering import *


def test_move_preserves_integrity_and_redundancy():
    move = TierMove(
        "a",
        "d",
        StorageTier("hot", True, 2),
        StorageTier("cold", True, 2),
        "m",
    )
    assert admit_move(move, TieringPolicy(2)).digest == "d"


def test_unavailable_or_under_redundant_target_rejected():
    with pytest.raises(PermissionError):
        admit_move(
            TierMove(
                "a",
                "d",
                StorageTier("hot", True, 2),
                StorageTier("cold", True, 1),
                "m",
            ),
            TieringPolicy(2),
        )
    with pytest.raises(IOError):
        admit_move(
            TierMove(
                "a",
                "d",
                StorageTier("hot", True, 2),
                StorageTier("cold", False, 2),
                "m",
            ),
            TieringPolicy(2),
        )


def test_same_tier_move_and_invalid_redundancy_rejected():
    tier = StorageTier("x", True, 2)
    with pytest.raises(ValueError):
        admit_move(TierMove("a", "d", tier, tier, "m"), TieringPolicy(1))
    with pytest.raises(ValueError):
        TieringPolicy(0)


def test_same_named_tier_alias_is_not_a_real_move():
    with pytest.raises(ValueError):
        admit_move(
            TierMove(
                "a",
                "d",
                StorageTier("hot", True, 1),
                StorageTier("hot", True, 3),
                "m",
            ),
            TieringPolicy(1),
        )


def test_tier_availability_and_redundancy_types_are_strict():
    with pytest.raises(ValueError):
        StorageTier("hot", 1, 2)
    with pytest.raises(ValueError):
        StorageTier("hot", True, True)
