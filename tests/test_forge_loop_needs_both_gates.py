"""A high blended score does not make a rejected project green."""

import pytest

from skeleton.forge.verify_loop import forge_verify_until_green


def test_project_rejection_is_not_overruled_by_a_script_score() -> None:
    result = forge_verify_until_green(
        {"player.gd": "extends Node\nfunc move():\n    return 1\n"},
        request="move the player",
        max_rounds=2,
        accept_threshold=0.7,
    )
    assert result["ok"] == 0
    assert result["accepted"] is False
    assert result["stopped_reason"] != "accepted"
    assert result["files"] == {"player.gd": "extends Node\nfunc move():\n    return 1\n"}
    with pytest.raises(ValueError):
        forge_verify_until_green({"player.gd": "extends Node\n"}, accept_threshold=0)
    with pytest.raises(ValueError):
        forge_verify_until_green({"player.gd": "extends Node\n"}, max_rounds=True)
