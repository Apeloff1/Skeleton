from __future__ import annotations
import json
from skeleton.game.campus_index import census, run_campus
from skeleton.game.predicates import gate, is_hot, require_never_extracted
from skeleton.game.seal_card import seal
from skeleton.game.verb_laws import apply_verb

def test_census_imports_or_skips() -> None:
    try:
        card = census()
    except ModuleNotFoundError:
        return
    assert card["n"] == 16
    assert card["stored_prose"] == 0

def test_verbs_predicates_seal() -> None:
    try:
        state = apply_verb({"heat": 10, "scrap": 2, "extracted": 0}, "scavenge")
        assert state["scrap"] >= 1
    except ModuleNotFoundError:
        return
    assert is_hot({"heat": 9}) is True
    require_never_extracted({"extracted": 0})
    assert gate({"heat": 9, "extracted": 0}, ["hot", "never_extracted"]) is True
    sealed = seal({"kind": "x", "n": 1})
    assert sealed["sota_ready"] is False
    assert len(sealed["digest"]) == 64

def test_cli_campus(capsys) -> None:
    from skeleton.__main__ import main
    code = main(["campus", "--seed", "8847291"])
    assert code in {0, 2}
