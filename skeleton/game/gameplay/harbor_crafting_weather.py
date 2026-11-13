"""Playable, source-bound weather and stamina simulation over canonical movement.

Every move is executed by the real game engine. Declarative weather and
hazards add deterministic costs and consequences; checkpoints are rebuilt
from the full event history rather than trusting saved overlay values.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import (
    HarborError, MAX_BUNDLE_BYTES, _identifier, _integer, _keys,
    canonical, digest, export_bundle, initial_state, step, validate_source,
    verify_bundle,
)
from .harbor_crafting_sessions import resume_bundle

BOARD_SCHEMA = "skeleton.game.harbor.weather-board.v1"
REPORT_SCHEMA = "skeleton.game.harbor.weather-report.v1"
FORECAST_SCHEMA = "skeleton.game.harbor.weather-forecast.v1"
MAX_BOARD_BYTES = 16384
MAX_REPORT_BYTES = MAX_BUNDLE_BYTES * 3
MAX_FORECAST_BYTES = MAX_REPORT_BYTES + 8192
MAX_PHASES = 16
MAX_HAZARDS = 16
WEATHER = {"clear": 0, "rain": 1, "storm": 2, "night": 1}
BOARD_FIELDS = {"schema", "source_id", "max_energy", "rest_gain", "phases", "hazards"}
REPORT_FIELDS = {
    "schema", "source", "board", "source_digest", "board_digest",
    "bundle", "events", "energy", "hazard_counts", "storm_moves",
    "rest_ticks", "report_digest",
}


def validate_weather(board: Any, source: Any) -> dict[str, Any]:
    world = validate_source(source)
    _keys(board, BOARD_FIELDS, "weather board")
    if board["schema"] != BOARD_SCHEMA or board["source_id"] != world["id"]:
        raise HarborError("weather board source mismatch")
    if len(canonical(board)) > MAX_BOARD_BYTES:
        raise HarborError("weather board exceeds byte limit")
    _integer(board["max_energy"], 1, 64, "max energy")
    _integer(board["rest_gain"], 1, 16, "rest gain")
    phases = board["phases"]
    if not isinstance(phases, list) or not 1 <= len(phases) <= MAX_PHASES:
        raise HarborError("invalid weather phases")
    previous = -1
    for phase in phases:
        _keys(phase, {"tick", "kind"}, "weather phase")
        tick = _integer(phase["tick"], 0, world["max_ticks"], "weather tick")
        if tick <= previous:
            raise HarborError("weather phases must be strictly increasing")
        if type(phase["kind"]) is not str or phase["kind"] not in WEATHER:
            raise HarborError("invalid weather kind")
        previous = tick
    if phases[0]["tick"] != 0:
        raise HarborError("weather phase must start at tick zero")
    hazards = board["hazards"]
    if not isinstance(hazards, list) or len(hazards) > MAX_HAZARDS:
        raise HarborError("invalid weather hazards")
    ids: set[str] = set()
    positions: set[tuple[int, int]] = set()
    for hazard in hazards:
        _keys(hazard, {"id", "at", "energy_cost"}, "weather hazard")
        name = _identifier(hazard["id"], "weather hazard id")
        pos = hazard["at"]
        if not isinstance(pos, list) or len(pos) != 2:
            raise HarborError("invalid hazard position")
        x = _integer(pos[0], 0, len(world["map"][0]) - 1, "hazard x")
        y = _integer(pos[1], 0, len(world["map"]) - 1, "hazard y")
        if world["map"][y][x] != ".":
            raise HarborError("weather hazard is blocked")
        _integer(hazard["energy_cost"], 1, 16, "hazard energy cost")
        if name in ids or (x, y) in positions:
            raise HarborError("duplicate weather hazard")
        ids.add(name)
        positions.add((x, y))
    return deepcopy(board)


def weather_at(board: dict[str, Any], tick: int) -> str:
    result = board["phases"][0]["kind"]
    for phase in board["phases"]:
        if phase["tick"] > tick:
            break
        result = phase["kind"]
    return result


def _simulate(world: dict[str, Any], board: dict[str, Any],
              actions: list[Any]) -> tuple[list[dict[str, Any]], int, dict[str, int], int, int]:
    state = initial_state(world)
    energy = board["max_energy"]
    counts = {hazard["id"]: 0 for hazard in board["hazards"]}
    events: list[dict[str, Any]] = []
    storm_moves = 0
    rest_ticks = 0
    previous = digest({"world": digest(world), "weather": digest(board), "genesis": True})
    for action in actions:
        next_tick = state["tick"] + 1
        weather = weather_at(board, next_tick)
        op = action["op"]
        before = energy
        if op == "wait":
            energy = min(board["max_energy"], energy + board["rest_gain"])
            rest_ticks += 1
        else:
            cost = 1 if op in ("move", "gather", "craft") else 0
            if op == "move":
                cost += WEATHER[weather]
                storm_moves += weather == "storm"
            if energy < cost:
                raise HarborError("weather exhaustion: rest before acting")
            energy -= cost
        advanced = step(world, state, action)
        triggered: list[str] = []
        if op == "move":
            for hazard in board["hazards"]:
                if advanced["pos"] == hazard["at"]:
                    if energy < hazard["energy_cost"]:
                        raise HarborError("hazard exhaustion: route unavailable")
                    energy -= hazard["energy_cost"]
                    counts[hazard["id"]] += 1
                    triggered.append(hazard["id"])
        entry = {
            "tick": next_tick, "action": deepcopy(action),
            "weather": weather, "energy_before": before,
            "energy_after": energy, "hazards": triggered,
            "position": list(advanced["pos"]), "state_digest": digest(advanced),
            "previous": previous,
        }
        entry["digest"] = digest(entry)
        events.append(entry)
        previous = entry["digest"]
        state = advanced
    return events, energy, counts, storm_moves, rest_ticks


def build_weather_game(source: Any, board: Any, actions: Any,
                       *, require_win: bool = False) -> dict[str, Any]:
    world = validate_source(source)
    authored = validate_weather(board, world)
    bundle = export_bundle(world, actions, require_win=require_win)
    events, energy, counts, storms, rests = _simulate(
        world, authored, [event["action"] for event in bundle["events"]]
    )
    report = {
        "schema": REPORT_SCHEMA, "source": world, "board": authored,
        "source_digest": digest(world), "board_digest": digest(authored),
        "bundle": bundle, "events": events, "energy": energy,
        "hazard_counts": counts, "storm_moves": storms, "rest_ticks": rests,
    }
    report["report_digest"] = digest(report)
    if len(canonical(report)) > MAX_REPORT_BYTES:
        raise HarborError("weather report exceeds byte limit")
    return report


def verify_weather_game(report: Any, *, require_win: bool = False) -> dict[str, Any]:
    _keys(report, REPORT_FIELDS, "weather report")
    if report["schema"] != REPORT_SCHEMA or len(canonical(report)) > MAX_REPORT_BYTES:
        raise HarborError("unsupported or oversized weather report")
    if report["report_digest"] != digest({
        key: value for key, value in report.items() if key != "report_digest"
    }):
        raise HarborError("weather report digest mismatch")
    verify_bundle(report["bundle"], require_win=require_win)
    actions = [event["action"] for event in report["bundle"]["events"]]
    rebuilt = build_weather_game(report["source"], report["board"], actions,
                                 require_win=require_win)
    if rebuilt != report:
        raise HarborError("weather gameplay replay mismatch")
    return {
        "energy": rebuilt["energy"], "storm_moves": rebuilt["storm_moves"],
        "hazard_counts": deepcopy(rebuilt["hazard_counts"]),
        "ending": rebuilt["bundle"]["state"]["ending"],
        "report_digest": rebuilt["report_digest"],
    }


def resume_weather_game(report: Any, actions: Any, *,
                        expected_digest: str, require_win: bool = False) -> dict[str, Any]:
    status = verify_weather_game(report)
    if type(expected_digest) is not str or expected_digest != status["report_digest"]:
        raise HarborError("stale weather checkpoint")
    if report["bundle"]["state"]["ending"] is not None:
        raise HarborError("weather campaign already complete")
    continued = resume_bundle(
        report["bundle"], actions,
        expected_terminal_digest=report["bundle"]["terminal_digest"],
        require_win=require_win,
    )
    rebuilt = build_weather_game(
        report["source"], report["board"],
        [event["action"] for event in continued["events"]],
        require_win=require_win,
    )
    if rebuilt["events"][:len(report["events"])] != report["events"]:
        raise HarborError("weather checkpoint history rewritten")
    return rebuilt


def weather_forecast(report: Any, *, horizon: int = 12) -> dict[str, Any]:
    verify_weather_game(report)
    _integer(horizon, 1, 64, "forecast horizon")
    current = report["bundle"]["state"]["tick"]
    end = min(current + horizon, report["source"]["max_ticks"])
    rows = [
        {"tick": tick, "weather": weather_at(report["board"], tick)}
        for tick in range(current + 1, end + 1)
    ]
    forecast = {
        "schema": FORECAST_SCHEMA, "report": deepcopy(report),
        "horizon": horizon, "rows": rows,
    }
    forecast["forecast_digest"] = digest(forecast)
    if len(canonical(forecast)) > MAX_FORECAST_BYTES:
        raise HarborError("weather forecast exceeds byte limit")
    return forecast


def verify_weather_forecast(forecast: Any) -> dict[str, Any]:
    _keys(forecast, {"schema", "report", "horizon", "rows", "forecast_digest"},
          "weather forecast")
    if (forecast["schema"] != FORECAST_SCHEMA
            or len(canonical(forecast)) > MAX_FORECAST_BYTES):
        raise HarborError("unsupported or oversized weather forecast")
    if forecast["forecast_digest"] != digest({
        key: value for key, value in forecast.items() if key != "forecast_digest"
    }):
        raise HarborError("weather forecast digest mismatch")
    rebuilt = weather_forecast(forecast["report"], horizon=forecast["horizon"])
    if rebuilt != forecast:
        raise HarborError("weather forecast replay mismatch")
    return {"rows": deepcopy(rebuilt["rows"]),
            "report_digest": rebuilt["report"]["report_digest"]}
