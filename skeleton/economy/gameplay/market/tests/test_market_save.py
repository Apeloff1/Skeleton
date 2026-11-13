"""Market saved as its own section through save_plane."""

from __future__ import annotations

import pytest

from skeleton.economy.gameplay.market.errors import ConservationError
from skeleton.economy.gameplay.market.exchange import PlayerMarket
from skeleton.economy.gameplay.market.save_section import (
    load_market,
    market_section,
    save_market,
    section_key,
)
from skeleton.economy.gameplay.market.tests.conftest import build_econ, funded
from skeleton.economy.gameplay.save import SaveError
from skeleton.kernel.game_save_plane import GameSavePlane


def _factory():
    return build_econ(owners=())


def _played():
    market = funded()
    market.mint_serialized("forge", "ana", "sword", ["sw-1"])
    market.place("ana", "sell", "ore", 10, 10, tick=1)
    market.place("bo", "buy", "ore", 4, 10, tick=2)
    market.place("cy", "buy", "herb", 3, 19, tick=3)
    market.place("ana", "sell", "sword", 1, 520, tick=4, serials=["sw-1"])
    market.wash.links.link("cy", "dee")
    market.advance(120)
    return market


def test_round_trip_restores_book_and_econ():
    plane = GameSavePlane()
    market = _played()
    save_market(plane, "s1", 1, market, other_sections={"runtime@v1": {"tick": 120}})
    sections, _ = plane.restore("s1")
    assert set(sections) >= {section_key(), "runtime@v1"}
    assert len(sections) == 3
    restored = load_market(plane, "s1", _factory)
    assert restored.digest() == market.digest()
    assert restored.econ.digest() == market.econ.digest()
    assert restored.audit()["ok"]
    # restored market keeps trading identically
    for m in (market, restored):
        m.place("dee", "buy", "ore", 6, 10, tick=130)
    assert restored.digest() == market.digest()


def test_rollback_to_earlier_sequence():
    plane = GameSavePlane()
    market = _played()
    save_market(plane, "s1", 1, market)
    first = market.digest()
    market.place("dee", "buy", "ore", 6, 10, tick=130)
    save_market(plane, "s1", 2, market)
    assert load_market(plane, "s1", _factory, sequence=1).digest() == first
    assert load_market(plane, "s1", _factory).digest() == market.digest()


def test_tampered_section_is_refused():
    plane = GameSavePlane()
    market = _played()
    sections = market_section(market)
    (key,) = sections
    sections[key]["state"]["book"] = []
    from skeleton.economy.gameplay import save_plane

    save_plane.save_to_plane(plane, "s1", 1, market.econ, other_sections=sections)
    with pytest.raises(SaveError, match="checksum"):
        load_market(plane, "s1", _factory)


def test_unbalanced_market_refused_on_save():
    market = _played()
    market.econ.grant_items("exploit", "cy", "sword", 1)
    with pytest.raises(ConservationError):
        save_market(GameSavePlane(), "s1", 1, market)


def test_duplicate_section_name_refused():
    market = _played()
    with pytest.raises(SaveError):
        save_market(GameSavePlane(), "s1", 1, market, other_sections={"market@v9": {}})


def test_state_round_trip_without_plane():
    market = _played()
    state = market.to_state()
    assert PlayerMarket.from_state(market.econ, state).to_state() == state
