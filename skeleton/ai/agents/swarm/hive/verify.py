"""Accept checks for GB-25."""

from __future__ import annotations

from typing import Any

from skeleton.hive.capabilities import capabilities
from skeleton.hive.engine import HiveEngine
from skeleton.hive.kernel import Hive
from skeleton.hive.law import WALK_CAP


def check_mint_link() -> None:
    h = Hive()
    a = h.mint("x")
    b = h.link(a["root"], "y")
    if not a["root"] or not b["root"]:
        raise AssertionError("mint")


def check_gossip() -> None:
    h = Hive()
    h.mint("a")
    g1 = h.gossip()
    g2 = h.gossip()
    if g2["n_history"] < 2 or not g1.get("consensus"):
        raise AssertionError("gossip")


def check_walk_cap() -> None:
    h2 = Hive()
    node = h2.mint("s")["root"]
    start = node
    for i in range(12):
        node = h2.link(node, "n%d" % i)["child"]
    path = h2.walk(start)["path"]
    if len(path) > WALK_CAP:
        raise AssertionError("walk")


def check_no_chain_coin() -> None:
    cap = capabilities()
    if cap["contract"]["chain"] != 0 or cap["contract"]["coin"] != 0:
        raise AssertionError("money")


def check_engine() -> None:
    card = HiveEngine().snapshot()
    if card["hit"] != 1 or card["stored_prose"] != 0:
        raise AssertionError("engine")


def run_all() -> dict[str, Any]:
    failed: list[str] = []
    for fn in (check_mint_link, check_gossip, check_walk_cap, check_no_chain_coin, check_engine):
        try:
            fn()
        except Exception as exc:
            failed.append(fn.__name__ + ":" + type(exc).__name__)
    return {"ok": int(not failed), "failed": failed, "n": 5}
