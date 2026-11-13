"""B025: economy save registered as one GameSavePlane section."""

from __future__ import annotations

import pytest

from skeleton.economy.gameplay.save import SAVE_VERSION, SaveError, save
from skeleton.economy.gameplay.save_plane import (
    economy_section,
    find_section,
    load_from_plane,
    save_to_plane,
    section_key,
)
from skeleton.economy.gameplay.tests.conftest import build_econ
from skeleton.kernel.game_save_plane import GameSavePlane


def _factory():
    return build_econ(owners=())


def _played():
    econ = build_econ()
    econ.grant("daily", "ana", tick=0)
    econ.vendor_buy("ana", "ore", 10)
    econ.charge("repair", "ana", 100)
    econ.grant_items("loot", "bo", "sword", 1)
    econ.bind("bo", "sword")
    return econ


def test_round_trip_through_plane_keeps_other_sections():
    plane = GameSavePlane()
    econ = _played()
    other = {"gameplay_runtime": {"tick": 7}}
    save_to_plane(plane, "s1", 1, econ, other_sections=other)
    sections, _ = plane.restore("s1")
    assert set(sections) == {"gameplay_runtime", section_key(SAVE_VERSION)}
    assert sections["gameplay_runtime"] == {"tick": 7}
    restored = load_from_plane(plane, "s1", _factory)
    assert restored.digest() == econ.digest()
    assert save(restored) == save(econ)


def test_rollback_to_earlier_sequence():
    plane = GameSavePlane()
    econ = _played()
    save_to_plane(plane, "s1", 1, econ)
    first = econ.digest()
    econ.vendor_sell("ana", "ore", 2)
    save_to_plane(plane, "s1", 2, econ)
    assert load_from_plane(plane, "s1", _factory, sequence=1).digest() == first
    assert load_from_plane(plane, "s1", _factory).digest() == econ.digest()


def test_v1_section_loads_through_plane():
    plane = GameSavePlane()
    v1 = {
        "version": 1,
        "balances": {"ana": {"gold": 700, "honor": 30}, "bo": {"gold": 5}},
        "inventories": {"ana": {"ore": 12}, "bo": {"sword": 1}},
    }
    plane.save("old", 1, {section_key(1): v1})
    econ = load_from_plane(plane, "old", _factory)
    assert econ.balance("ana", "gold") == 700
    assert econ.inventory("bo").count("sword") == 1
    assert econ.audit()["ok"] and econ.item_audit()["ok"]


def test_v2_section_loads_through_plane():
    plane = GameSavePlane()
    v2 = {
        "version": 2,
        "balances": {"gold": {"__sink__": 40, "ana": 60}},
        "inventories": {"ana": {"owner": "ana", "slots": None, "stacks": {"ore": 3}}},
    }
    plane.save("old", 1, {section_key(2): v2})
    econ = load_from_plane(plane, "old", _factory)
    assert econ.balance("ana", "gold") == 60
    assert econ.flow_report("gold")["burned"] == 40
    assert econ.audit()["ok"]


def test_unknown_version_rejected():
    plane = GameSavePlane()
    future = {"version": SAVE_VERSION + 1, "state": {}, "checksum": ""}
    plane.save("new", 1, {section_key(SAVE_VERSION + 1): future})
    with pytest.raises(SaveError, match="unknown"):
        load_from_plane(plane, "new", _factory)
    with pytest.raises(SaveError, match="unknown"):
        find_section({section_key(0): {"version": 0}})


def test_key_payload_mismatch_and_missing_or_duplicate_rejected():
    data = economy_section(_played())
    payload = next(iter(data.values()))
    with pytest.raises(SaveError, match="disagree"):
        find_section({section_key(2): payload})
    with pytest.raises(SaveError, match="no 'economy'"):
        find_section({"gameplay_runtime": {}})
    with pytest.raises(SaveError, match="more than one"):
        find_section({section_key(3): payload, section_key(2): {"version": 2}})
    with pytest.raises(SaveError, match="already holds"):
        save_to_plane(GameSavePlane(), "s", 1, _played(), other_sections=data)
