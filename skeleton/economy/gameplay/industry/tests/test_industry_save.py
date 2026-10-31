"""industry@v1 save section through save_plane / market save."""

from __future__ import annotations

import pytest

from skeleton.economy.gameplay import save_plane
from skeleton.economy.gameplay.industry.save_section import (
    industry_section,
    load_industry,
    save_industry,
)
from skeleton.economy.gameplay.industry.tests.conftest import build_econ, stocked
from skeleton.economy.gameplay.save import SaveError
from skeleton.kernel.game_save_plane import GameSavePlane


def _empty():
    return build_econ(owners=())


def _played(market: bool = False):
    s = stocked(market=market)
    s.queue_chain("ana", "hull", 1, tick=0)
    s.queue_research("bo", "press_plate", "te", tick=1)
    s.extract("bo", "vein_a", tick=2)
    s.advance(40)
    return s


@pytest.mark.parametrize("market", [False, True])
def test_round_trip_and_resume(market):
    plane = GameSavePlane()
    s = _played(market)
    save_industry(plane, "s1", 1, s)
    back = load_industry(plane, "s1", _empty, with_market=market)
    assert back.digest() == s.digest()
    s.advance(10_000)
    back.advance(10_000)
    assert back.digest() == s.digest() and back.audit()["ok"]


def test_rollback_to_earlier_sequence():
    plane = GameSavePlane()
    s = _played()
    save_industry(plane, "s1", 1, s)
    first = s.digest()
    s.advance(10_000)
    save_industry(plane, "s1", 2, s)
    assert load_industry(plane, "s1", _empty, sequence=1).digest() == first
    assert load_industry(plane, "s1", _empty).digest() == s.digest()


def test_tampered_section_refused():
    plane = GameSavePlane()
    s = _played()
    sections = industry_section(s)
    (key,) = sections
    sections[key]["state"]["nodes"] = {}
    save_plane.save_to_plane(plane, "s1", 1, s.econ, other_sections=sections)
    with pytest.raises(SaveError, match="checksum"):
        load_industry(plane, "s1", _empty)


def test_missing_section_and_duplicates_refused():
    plane = GameSavePlane()
    s = _played()
    save_plane.save_to_plane(plane, "s1", 1, s.econ)
    with pytest.raises(SaveError):
        load_industry(plane, "s1", _empty)
    with pytest.raises(SaveError):
        save_industry(plane, "s2", 1, s, other_sections={"industry@v9": {}})


def test_unbalanced_refused_on_save():
    s = _played()
    s.econ.consume_items("craft_loss", "ana", "ore", 1)
    with pytest.raises(Exception):
        save_industry(GameSavePlane(), "s1", 1, s)
