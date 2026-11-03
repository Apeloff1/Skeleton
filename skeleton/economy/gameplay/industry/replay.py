"""Command scripts and replay-determinism for industry.

Same contract as :mod:`skeleton.economy.gameplay.market.replay`: a script
is a list of plain dicts, refused commands are recorded rather than raised,
and the same script on a fresh system always yields the same digest.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, Mapping

from skeleton.economy.gameplay.industry.engine import IndustrySystem
from skeleton.economy.gameplay.industry.errors import IndustryError

MAX_SCRIPT_COMMANDS = 100_000
from skeleton.simulation.economy.sim import EconomySimError


def apply(system: IndustrySystem, cmd: Mapping[str, Any]) -> Any:
    op = cmd["op"]
    econ = system.econ
    if op == "grant":
        return econ.grant(cmd["faucet"], cmd["owner"], cmd["tick"])
    if op == "grant_items":
        return econ.grant_items(
            cmd["source"], cmd["owner"], cmd["item"], cmd.get("qty", 1)
        )
    if op == "set_lines":
        return system.set_lines(cmd["owner"], cmd["lines"])
    if op == "build":
        return system.queue_build(
            cmd["owner"], cmd["bp"], cmd.get("runs", 1), cmd["tick"]
        )
    if op == "chain":
        return system.queue_chain(cmd["owner"], cmd["target"], cmd["qty"], cmd["tick"])
    if op == "research":
        return system.queue_research(cmd["owner"], cmd["bp"], cmd["track"], cmd["tick"])
    if op == "cancel":
        return system.cancel(cmd["owner"], cmd["job_id"], cmd["tick"])
    if op == "collect":
        return system.collect(cmd["owner"], cmd["job_id"], cmd["tick"])
    if op == "extract":
        return system.extract(cmd["owner"], cmd["node"], cmd["tick"])
    if op == "list":
        return system.list_output(
            cmd["owner"], cmd["item"], cmd["qty"], cmd["price"], cmd["tick"]
        )
    if op == "buy":
        return system.buy_inputs(
            cmd["owner"], cmd["item"], cmd["qty"], cmd["price"], cmd["tick"]
        )
    if op == "advance":
        return system.advance(cmd["tick"])
    raise ValueError(f"unknown op {op!r}")


def run(
    build: Callable[[], IndustrySystem], script: Iterable[Mapping[str, Any]]
) -> tuple[IndustrySystem, list[Any]]:
    system = build()
    results: list[Any] = []
    for index, cmd in enumerate(script):
        if index >= MAX_SCRIPT_COMMANDS:
            raise IndustryError("industry replay script command budget exceeded")
        try:
            results.append(apply(system, cmd))
        except EconomySimError as exc:
            results.append({"refused": type(exc).__name__, "reason": str(exc)})
    return system, results


def fingerprint(
    build: Callable[[], IndustrySystem], script: Iterable[Mapping[str, Any]]
) -> str:
    system, _ = run(build, script)
    return system.digest()


__all__ = ["apply", "fingerprint", "run"]
