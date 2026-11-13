"""B025: versioned economy saves, migrations and audit-on-load."""

from __future__ import annotations

import copy

import pytest

from skeleton.economy.gameplay.save import SAVE_VERSION, SaveError, load, migrate, save
from skeleton.economy.gameplay.tests.conftest import build_econ


def _factory():
    return build_econ(owners=())


def _played():
    econ = build_econ()
    econ.grant("daily", "ana", tick=0)
    econ.vendor_buy("ana", "ore", 10)
    econ.charge("repair", "ana", 100)
    econ.grant_items("loot", "bo", "sword", 1)
    econ.bind("bo", "sword")
    econ.grant("arena", "bo", tick=0)
    return econ


def test_save_load_round_trip_is_exact():
    econ = _played()
    data = save(econ)
    assert data["version"] == SAVE_VERSION
    restored = load(copy.deepcopy(data), _factory)
    assert restored.digest() == econ.digest()
    assert restored.flow_report("gold") == econ.flow_report("gold")
    assert restored.item_report("sword") == econ.item_report("sword")
    assert restored.bound_count("bo", "sword") == 1
    assert save(restored) == data
    # restored economy keeps working with its invariants
    restored.vendor_sell("ana", "ore", 2)
    assert restored.audit()["ok"] and restored.item_audit()["ok"]


def test_tampered_save_is_refused():
    data = save(_played())
    data["state"]["balances"]["gold"]["ana"] += 1_000_000
    with pytest.raises(SaveError, match="checksum"):
        load(data, _factory)


def test_consistent_but_unbalanced_state_is_refused():
    data = save(_played())
    data["state"]["balances"]["gold"]["ana"] += 5
    from skeleton.economy.gameplay.save import _checksum

    data["checksum"] = _checksum(data["state"])
    with pytest.raises(SaveError, match="do not balance"):
        load(data, _factory)


def test_v1_save_migrates_to_v3_and_loads():
    v1 = {
        "version": 1,
        "balances": {"ana": {"gold": 700, "honor": 30}, "bo": {"gold": 5}},
        "inventories": {"ana": {"ore": 12}, "bo": {"sword": 1}},
    }
    v3 = migrate(v1)
    assert v3["version"] == 3
    assert v3["state"]["flows"]["gold"]["by_faucet"] == {"migration": 705}
    assert v3["state"]["item_flows"]["ore"]["minted"] == 12
    econ = load(v1, _factory)
    assert econ.balance("ana", "gold") == 700
    assert econ.balance("ana", "honor") == 30
    assert econ.inventory("bo").count("sword") == 1
    assert econ.audit()["ok"] and econ.item_audit()["ok"]


def test_v2_burn_account_becomes_burned_flow():
    v2 = {
        "version": 2,
        "balances": {"gold": {"__sink__": 40, "ana": 60}},
        "inventories": {"ana": {"owner": "ana", "slots": 6, "stacks": {}}},
    }
    econ = load(v2, _factory)
    report = econ.flow_report("gold")
    assert (report["minted"], report["burned"], report["circulating"]) == (100, 40, 60)
    assert econ.inventory("ana").slots == 6


@pytest.mark.parametrize(
    "data, message",
    [
        ({"version": 99}, "newer build"),
        ({"version": 0}, "valid version"),
        ({"version": True}, "valid version"),
        ({}, "valid version"),
        ({"version": 1, "balances": {"ana": 5}}, "malformed"),
        ({"version": 1, "balances": {"ana": {"zinc": 5}}}, "unknown currency"),
        ({"version": 1, "inventories": {"ana": {"ghost": 1}}}, "unknown item"),
        ({"version": 1, "inventories": {"ana": {"sword": 9}}}, "exceeds its slots"),
    ],
)
def test_bad_saves_fail_closed(data, message):
    with pytest.raises(SaveError, match=message):
        load(data, _factory)


def test_factory_must_be_empty():
    with pytest.raises(SaveError, match="empty"):
        load(save(_played()), build_econ)
