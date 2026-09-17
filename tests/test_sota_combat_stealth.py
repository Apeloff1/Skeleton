from __future__ import annotations

from skeleton.game.combat_pack import bout
from skeleton.game.dream_pack import apply as dream
from skeleton.game.economy_pack import apply_offer
from skeleton.game.los_pack import visible
from skeleton.game.stealth_pack import apply as stealth


def test_combat_bout() -> None:
    card = bout(["jab", "slash", "bash", "warphit"], 8847291)
    assert card["winner"] in {"player", "foe", "draw"}
    assert card["hits"]


def test_stealth_economy_dream_los() -> None:
    s = stealth({"alert": 2, "heat": 4}, "quiet", False)
    assert s["stance"] == "quiet"
    bag = apply_offer({"scrap": 4, "parts": 0}, "scrap_for_parts")
    assert bag["parts"] == 1
    d = dream({"sleep": 8, "extracted": 0, "slept": 0}, "deep")
    assert d["slept"] == 1
    assert visible(["empty", "heat", "extract"], 0, 2) is True
