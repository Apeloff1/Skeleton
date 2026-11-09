"""GB-12 product cycle: pointer parse, lazy doctor/nervous/product."""

from __future__ import annotations

import sys
import types

from skeleton.jeeves import Jeeves
from skeleton.jeeves.core import Jeeves as CoreJeeves
from skeleton.jeeves.core import JeevesCore
from skeleton.jeeves.product_cycle import (
    N_CAP,
    ProductCycle,
    parse_pointers,
    run_cycle,
)


def test_core_alias_still_tutor_jeeves() -> None:
    assert JeevesCore is CoreJeeves
    assert hasattr(JeevesCore, "plan_build")
    assert hasattr(JeevesCore, "doctor")
    assert hasattr(JeevesCore, "nervous")
    assert hasattr(JeevesCore, "product")
    assert hasattr(JeevesCore, "cycle")


def test_parse_pointers_keeps_urls_and_zero_prose() -> None:
    card = parse_pointers(
        "see https://arxiv.org/abs/1706.03762 and github.com/Apeloff1/Skeleton please"
    )
    assert card["kind"] == "parse"
    assert card["n"] == 2
    assert card["stored_prose"] == 0
    assert card["hit"] == 1
    joined = " ".join(card["pointers"])
    assert "arxiv.org/abs/1706.03762" in joined
    assert "github.com/Apeloff1/Skeleton" in joined
    assert "please" not in joined


def test_parse_pointers_caps_and_drops_without_prose_spill() -> None:
    urls = " ".join(f"https://example.com/p/{i}" for i in range(N_CAP + 3))
    card = parse_pointers(f"long sentence about meaning {urls}")
    assert card["n"] == N_CAP
    assert card["dropped"] == 3
    assert card["hit"] == 0
    assert card["law"] == "n-cap"
    assert card["stored_prose"] == 0
    assert "long sentence" not in repr(card["pointers"])


def test_parse_rejects_non_string() -> None:
    try:
        parse_pointers(123)  # type: ignore[arg-type]
    except TypeError:
        return
    raise AssertionError("expected TypeError")


def test_doctor_does_not_import_organism_doctor() -> None:
    fake = types.ModuleType("skeleton.organism")
    broken = types.ModuleType("skeleton.organism.doctor")

    def _boom(*_a, **_k):
        raise RuntimeError("organism.doctor must stay lazy")

    broken.diagnose = _boom
    sys.modules["skeleton.organism"] = fake
    sys.modules["skeleton.organism.doctor"] = broken
    import skeleton.cortex.deck  # noqa: F401

    j = Jeeves()
    card = j.doctor("https://arxiv.org/abs/1406.2661")
    assert card["kind"] == "doctor"
    assert card["stored_prose"] == 0
    assert sys.modules["skeleton.organism.doctor"] is broken


def test_nervous_halts_on_collapsed_walk() -> None:
    j = Jeeves()
    j.last_walk = {"extracted": False, "collapsed": True, "era": "extraction_now", "slack": 0.0}
    card = j.nervous()
    assert card["kind"] == "nervous"
    assert card["law"] == "halt"
    assert card["hit"] == 0
    assert card["stored_prose"] == 0


def test_product_does_not_ship_when_halted() -> None:
    j = Jeeves()
    artifact = j.product(walk={"extracted": False, "collapsed": True, "slack": 0.0})
    assert artifact["kind"] == "product"
    assert artifact["ship"] is False
    assert artifact["law"] == "halt"
    assert artifact["stored_prose"] == 0


def test_cycle_is_deterministic_and_can_build() -> None:
    j = Jeeves()
    stim = "https://github.com/Apeloff1/Skeleton"
    a = j.cycle(stim, build=True)
    b = j.cycle(stim, build=True)
    assert a["kind"] == "cycle"
    assert a["stages"] == ("parse", "doctor", "nervous", "product")
    assert a["stored_prose"] == 0
    assert a["fingerprint"] == b["fingerprint"]
    assert j.last_plan is not None
    assert a["plan"].get("seed")


def test_product_cycle_without_host_is_self_contained() -> None:
    card = run_cycle("https://arxiv.org/abs/2005.14165", pack={"era": "extraction_now"})
    assert card["kind"] == "cycle"
    assert card["doctor"]["era"] == "extraction_now"
    assert card["stored_prose"] == 0
    assert ProductCycle().doctor("https://arxiv.org/abs/2005.14165")["pointers"]
