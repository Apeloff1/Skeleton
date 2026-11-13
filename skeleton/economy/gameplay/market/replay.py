"""Command scripts and replay-determinism for the player market.

A *script* is a list of plain dicts. :func:`apply` executes one command
against a market (and its economy); :func:`run` builds a fresh market and
applies a whole script, recording refusals instead of stopping, so the same
script always yields the same :meth:`PlayerMarket.digest`.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, Mapping

from skeleton.economy.gameplay.market.exchange import PlayerMarket
from skeleton.economy.gameplay.market.errors import MarketError

MAX_SCRIPT_COMMANDS = 100_000
from skeleton.simulation.economy.sim import EconomySimError


def apply(market: PlayerMarket, cmd: Mapping[str, Any]) -> Any:
    op = cmd["op"]
    econ = market.econ
    if op == "open":
        return econ.open_account(cmd["owner"])
    if op == "grant":
        return econ.grant(cmd["faucet"], cmd["owner"], cmd["tick"])
    if op == "grant_items":
        return econ.grant_items(
            cmd["source"], cmd["owner"], cmd["item"], cmd.get("qty", 1)
        )
    if op == "vendor_buy":
        return econ.vendor_buy(cmd["owner"], cmd["item"], cmd.get("qty", 1))
    if op == "link":
        return market.wash.links.link(cmd["a"], cmd["b"], cmd.get("reason", "declared"))
    if op == "mint_serialized":
        return market.mint_serialized(
            cmd["source"], cmd["owner"], cmd["item"], cmd["serials"]
        )
    if op == "place":
        return market.place(
            cmd["owner"],
            cmd["side"],
            cmd["item"],
            cmd["qty"],
            cmd["price"],
            cmd["tick"],
            ttl=cmd.get("ttl"),
            tif=cmd.get("tif", "gtc"),
            serials=cmd.get("serials", ()),
        )
    if op == "cancel":
        return market.cancel(cmd["owner"], cmd["order_id"], cmd["tick"])
    if op == "claim":
        return market.claim(cmd["owner"], cmd["item"], cmd["tick"])
    if op == "advance":
        return market.advance(cmd["tick"])
    raise ValueError(f"unknown op {op!r}")


def run(
    build: Callable[[], PlayerMarket], script: Iterable[Mapping[str, Any]]
) -> tuple[PlayerMarket, list[Any]]:
    """Apply ``script`` to a fresh market; refused commands yield ``{"refused": code}``."""
    market = build()
    results: list[Any] = []
    for index, cmd in enumerate(script):
        if index >= MAX_SCRIPT_COMMANDS:
            raise MarketError("market replay script command budget exceeded")
        try:
            results.append(apply(market, cmd))
        except EconomySimError as exc:
            results.append({"refused": type(exc).__name__, "reason": str(exc)})
    return market, results


def fingerprint(
    build: Callable[[], PlayerMarket], script: Iterable[Mapping[str, Any]]
) -> str:
    market, _ = run(build, script)
    return market.digest()


__all__ = ["apply", "fingerprint", "run"]
