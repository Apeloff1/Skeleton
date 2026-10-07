from __future__ import annotations

from skeleton.persistence.spine_masterplan import SpineMasterplan


def test_masterplan_card_is_unsigned() -> None:
    card = SpineMasterplan().card()
    assert card["doc"] == "docs/plan/P2_SPINE_MASTERPLAN.md"
    assert card["read_project_percent"] == 100
    assert card["apply_percent"] == 99
    assert card["motor_bootstrap_percent"] == 100
    assert card["merge_percent"] == 0
    assert card["bind_card_percent"] == 100
    assert card["hit"] is False
    assert card["completion_checkbox"] is False
