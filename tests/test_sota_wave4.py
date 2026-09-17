from __future__ import annotations

import json

from skeleton.game.wave4_index import census
from skeleton.game.wave4_play import play


def test_wave4_play() -> None:
    left = play(seed=8847291)
    right = play(seed=8847291)
    assert left["digest"] == right["digest"]
    assert left["packs"] >= 20
    assert left["sota_ready"] is False
    assert census()["n"] == left["packs"]


def test_cli_wave4(capsys) -> None:
    from skeleton.__main__ import main

    assert main(["wave4", "--seed", "8847291"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["sota_ready"] is False
