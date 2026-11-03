"""Replay determinism and conservation under randomized scripts."""

from __future__ import annotations

import random

from skeleton.economy.gameplay.market.exchange import ESCROW_OWNER
from skeleton.economy.gameplay.market.replay import fingerprint, run
from skeleton.economy.gameplay.market.tests.conftest import OWNERS, build_market

ITEMS = {"ore": 10, "herb": 20, "sword": 500}


def _script(seed: int, steps: int = 400) -> list[dict]:
    rng = random.Random(seed)
    cmds: list[dict] = []
    for o in OWNERS:
        cmds += [
            {"op": "grant", "faucet": "daily", "owner": o, "tick": 0},
            {
                "op": "grant_items",
                "source": "mine",
                "owner": o,
                "item": "ore",
                "qty": 60,
            },
            {
                "op": "grant_items",
                "source": "garden",
                "owner": o,
                "item": "herb",
                "qty": 40,
            },
        ]
    cmds.append(
        {
            "op": "mint_serialized",
            "source": "forge",
            "owner": "ana",
            "item": "sword",
            "serials": ["s1", "s2"],
        }
    )
    cmds.append(
        {
            "op": "mint_serialized",
            "source": "forge",
            "owner": "bo",
            "item": "sword",
            "serials": ["s3"],
        }
    )
    if seed % 2:
        cmds.append({"op": "link", "a": "cy", "b": "dee"})
    tick = 1
    oid = 0
    for _ in range(steps):
        tick += rng.randint(0, 7)
        roll = rng.random()
        owner = rng.choice(OWNERS)
        if roll < 0.7:
            item = rng.choice(["ore", "ore", "herb", "sword"])
            ref = ITEMS[item]
            price = max(1, ref + rng.randint(-ref // 2, ref // 2))
            side = rng.choice(["buy", "sell"])
            qty = 1 if item == "sword" else rng.randint(1, 15)
            cmd = {
                "op": "place",
                "owner": owner,
                "side": side,
                "item": item,
                "qty": qty,
                "price": price,
                "tick": tick,
                "tif": rng.choice(["gtc", "gtc", "ioc"]),
            }
            if rng.random() < 0.3:
                cmd["ttl"] = rng.randint(1, 60)
            if item == "sword" and side == "sell":
                cmd["serials"] = [rng.choice(["s1", "s2", "s3", "s4"])]
            cmds.append(cmd)
            oid += 1
        elif roll < 0.85:
            cmds.append(
                {
                    "op": "cancel",
                    "owner": owner,
                    "order_id": rng.randint(1, max(1, oid)),
                    "tick": tick,
                }
            )
        elif roll < 0.92:
            cmds.append(
                {
                    "op": "claim",
                    "owner": owner,
                    "item": rng.choice(list(ITEMS)),
                    "tick": tick,
                }
            )
        else:
            cmds.append({"op": "advance", "tick": tick})
    return cmds


def _build():
    return build_market(refs={"herb": 20, "sword": 500})


def test_same_script_same_fingerprint():
    for seed in range(4):
        script = _script(seed)
        assert fingerprint(_build, script) == fingerprint(_build, script)


def test_different_scripts_differ():
    assert fingerprint(_build, _script(1)) != fingerprint(_build, _script(2))


def test_random_scripts_conserve_money_items_and_serials():
    for seed in range(12):
        market, results = run(_build, _script(seed))
        report = market.audit()
        assert report["ok"], (seed, report)
        assert any(isinstance(r, dict) and r.get("fills") for r in results), seed
        # sinks are the only place gold left the players + escrow
        flows = market.econ.flow_report("gold")
        assert flows["by_sink"].get("market_listing", 0) > 0
        assert market.balance(ESCROW_OWNER) == sum(
            o.unit_price * o.remaining for o in market.book.orders() if o.side == "buy"
        )


def test_refusals_change_nothing():
    market, _ = run(_build, _script(3, steps=50))
    before = market.digest()
    econ_before = market.econ.digest()
    t = market._tick  # same tick: nothing expires or closes
    _, results = run(
        lambda: market,
        [
            {
                "op": "place",
                "owner": "ana",
                "side": "sell",
                "item": "ore",
                "qty": 10**6,
                "price": 10,
                "tick": t,
            },
            {"op": "cancel", "owner": "bo", "order_id": 10**9, "tick": t},
            {
                "op": "place",
                "owner": "nobody",
                "side": "buy",
                "item": "ore",
                "qty": 1,
                "price": 10,
                "tick": t,
            },
        ],
    )
    assert all("refused" in r for r in results)
    assert market.econ.digest() == econ_before
    assert market.digest() == before


def test_drain_after_cancel_all_returns_everything():
    market, _ = run(_build, _script(5))
    tick = market._tick + 1
    for order in list(market.book.orders()):
        market.cancel(order.owner, order.order_id, tick)
    for owner in OWNERS:
        for item in ITEMS:
            try:
                market.claim(owner, item, tick)
            except Exception:
                pass
    assert len(market.book) == 0
    assert market.balance(ESCROW_OWNER) == 0
    assert market.audit()["ok"]


def test_market_replay_rejects_unbounded_script_iterators(monkeypatch):
    from itertools import repeat
    import pytest
    from skeleton.economy.gameplay.market import replay as replay_module
    from skeleton.economy.gameplay.market.errors import MarketError

    monkeypatch.setattr(replay_module, "MAX_SCRIPT_COMMANDS", 3)
    cmd = {"op": "open", "owner": "ana"}
    with pytest.raises(MarketError, match="command budget"):
        replay_module.run(_build, repeat(cmd))
    with pytest.raises(MarketError, match="command budget"):
        replay_module.fingerprint(_build, repeat(cmd))
