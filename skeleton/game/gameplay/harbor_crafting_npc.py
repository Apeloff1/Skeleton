"""Source-bound NPC patrol, trade reachability and deterministic observation."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import (
    HarborError, MAX_BUNDLE_BYTES, MAX_INVENTORY, _keys, canonical, digest,
    initial_state, step, verify_bundle,
)
from .harbor_crafting_sessions import resume_bundle

SCHEMA = "skeleton.game.harbor.npc-observations.v1"
FORECAST_SCHEMA = "skeleton.game.harbor.npc-forecast.v1"
MAX_BYTES = MAX_BUNDLE_BYTES * 6
MAX_FORECAST = 32


def _observe(state: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    distance = abs(state["pos"][0] - state["npc_pos"][0]) + abs(state["pos"][1] - state["npc_pos"][1])
    can_trade = (
        distance == 1
        and state["ending"] is None
        and state["coins"] >= source["npc"]["price"]
        and sum(state["inventory"].values()) < MAX_INVENTORY
        and any(quantity > 0 for quantity in state["npc_stock"].values())
    )
    return {
        "tick": state["tick"],
        "player": list(state["pos"]),
        "npc": list(state["npc_pos"]),
        "distance": distance,
        "trade_reachable": can_trade,
        "stock": deepcopy(state["npc_stock"]),
        "coins": state["coins"],
        "merchant_price": source["npc"]["price"],
        "ending": state["ending"],
        "state_digest": digest(state),
    }


def npc_observations(bundle: Any) -> dict[str, Any]:
    """Observe every actual patrol tick, including blocked NPC movement."""
    verify_bundle(bundle)
    source = bundle["source"]
    state = initial_state(source)
    entries = [{"sequence": 0, "event_digest": None, **_observe(state, source)}]
    for index, event in enumerate(bundle["events"]):
        state = step(source, state, event["action"])
        if digest(state) != event["after"]:
            raise HarborError("NPC event replay mismatch")
        entries.append({
            "sequence": index + 1,
            "event_digest": event["digest"],
            **_observe(state, source),
        })
    if state != bundle["state"]:
        raise HarborError("NPC terminal replay mismatch")
    result = {
        "schema": SCHEMA,
        "bundle": deepcopy(bundle),
        "source_digest": bundle["source_digest"],
        "terminal_digest": bundle["terminal_digest"],
        "entries": entries,
    }
    result["report_digest"] = digest(result)
    if len(canonical(result)) > MAX_BYTES:
        raise HarborError("NPC observation report exceeds byte limit")
    return result


def verify_npc_observations(report: Any) -> dict[str, Any]:
    _keys(report, {"schema", "bundle", "source_digest", "terminal_digest", "entries", "report_digest"}, "NPC observations")
    if report["schema"] != SCHEMA or len(canonical(report)) > MAX_BYTES:
        raise HarborError("unsupported or oversized NPC observations")
    if report["report_digest"] != digest({k: v for k, v in report.items() if k != "report_digest"}):
        raise HarborError("NPC observation digest mismatch")
    rebuilt = npc_observations(report["bundle"])
    if rebuilt != report:
        raise HarborError("NPC observation replay mismatch")
    return deepcopy(rebuilt["entries"][-1])


def npc_forecast(bundle: Any, ticks: int) -> dict[str, Any]:
    """Preview bounded WAIT-only patrol futures; not a claim about player choices."""
    verify_bundle(bundle)
    if type(ticks) is not int or not 1 <= ticks <= MAX_FORECAST:
        raise HarborError("NPC forecast tick count invalid")
    if bundle["state"]["ending"] is not None:
        raise HarborError("NPC forecast cannot advance completed game")
    if len(bundle["events"]) + ticks > bundle["source"]["max_ticks"]:
        raise HarborError("NPC forecast exceeds tick budget")
    actions = [{"op": "wait"} for _ in range(ticks)]
    future = resume_bundle(
        bundle, actions, expected_terminal_digest=bundle["terminal_digest"])
    observation = npc_observations(future)
    entries = observation["entries"][len(bundle["events"]) + 1:]
    result = {
        "schema": FORECAST_SCHEMA,
        "root": deepcopy(bundle),
        "root_digest": bundle["bundle_digest"],
        "ticks": ticks,
        "actions": actions,
        "entries": entries,
        "terminal_digest": future["terminal_digest"],
    }
    result["forecast_digest"] = digest(result)
    if len(canonical(result)) > MAX_BYTES:
        raise HarborError("NPC forecast exceeds byte limit")
    return result


def verify_npc_forecast(forecast: Any) -> dict[str, Any]:
    _keys(forecast, {
        "schema", "root", "root_digest", "ticks", "actions",
        "entries", "terminal_digest", "forecast_digest",
    }, "NPC forecast")
    if forecast["schema"] != FORECAST_SCHEMA or len(canonical(forecast)) > MAX_BYTES:
        raise HarborError("unsupported or oversized NPC forecast")
    if forecast["forecast_digest"] != digest({
        k: v for k, v in forecast.items() if k != "forecast_digest"
    }):
        raise HarborError("NPC forecast digest mismatch")
    if not isinstance(forecast["root"], dict) or forecast["root_digest"] != forecast["root"].get("bundle_digest"):
        raise HarborError("NPC forecast root mismatch")
    rebuilt = npc_forecast(forecast["root"], forecast["ticks"])
    if rebuilt != forecast:
        raise HarborError("NPC forecast replay mismatch")
    return deepcopy(rebuilt["entries"][-1])
