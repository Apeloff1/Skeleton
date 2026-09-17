from __future__ import annotations

import json

from skeleton.game.encounter_pack import run as enc_run
from skeleton.game.extract_ledger import play as ledger
from skeleton.game.hunt_field import play as hunt
from skeleton.game.law_composer import play as compose
from skeleton.game.law_index import census
from skeleton.game.status_laws import apply, tick_named
from skeleton.game.verb_pack import apply as vapply


def test_status_and_verb() -> None:
    state = apply({"heat": 1, "tokens": 8, "status": {}, "extracted": 0}, "burn", 2)
    state = tick_named(state)
    assert "burn" in state["status"]
    state = vapply({"heat": 8, "tokens": 8, "extracted": 0, "sleep": 0}, "wait")
    assert state["sleep"] >= 1


def test_encounter_and_ledger() -> None:
    enc = enc_run("extract_herald", 8847291, ["extract", "seal"])
    assert enc["done"] is True
    card = ledger(seed=8847291)
    assert card["extract_count"] == 1
    assert card["denied"] == 1


def test_hunt_and_composer() -> None:
    h = hunt(seed=8847291, ticks=16)
    assert h["hunters"] == 8
    c = compose(seed=8847291)
    assert c["ledger"] == 1
    assert c["sota_ready"] is False
    assert census()["n"] >= 20


def test_cli_laws(capsys) -> None:
    from skeleton.__main__ import main

    assert main(["laws", "--seed", "8847291"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["sota_ready"] is False
    assert payload["extract_count"] == 1
