"""Closed set of recovered gameplay owners for composite GameForge sagas.

No dynamic adapter import or executable package is accepted. These owners
already implement survey, weather, dialogue, convoy and contract rules.
Adapters verify their reports independently and expose compact summaries;
full reports can be regenerated on demand from the independently held source.
"""
from __future__ import annotations

from typing import Any

from skeleton.app.gameforge_campaign import detached, digest
from skeleton.app.original_quest_cli import _encode, _object, _require, _text
from skeleton.game.gameplay import harbor_crafting as harbor
from skeleton.game.gameplay import harbor_crafting_convoy as convoy
from skeleton.game.gameplay import harbor_crafting_convoy_contracts as contracts
from skeleton.game.gameplay import harbor_crafting_expedition as exploration
from skeleton.game.gameplay.harbor_crafting_expedition_ui import render_map

KINDS = frozenset({"survey_expedition", "convoy_contract"})
MAX_TURNS = 256
MAX_CANDIDATES = 128


def admit_episode(raw: Any) -> dict:
    row = _object(detached(raw), {"objective", "kind", "source", "rules", "witness"})
    _text(row["objective"], 128)
    kind = _text(row["kind"], 32)
    _require(kind in KINDS, "unknown saga gameplay owner")
    world = harbor.validate_source(row["source"])
    _require(world["max_ticks"] <= MAX_TURNS, "saga local tick ceiling exceeded")
    rules = row["rules"]
    if kind == "survey_expedition":
        rules = _object(rules, {"survey", "weather", "dialogue", "required_ending"})
        _require(rules["required_ending"] in ("beacon", "safe_harbor"),
                 "unsupported survey expedition ending")
        package = exploration.build_expedition_package(
            world["id"], world, rules["survey"], rules["weather"], rules["dialogue"])
        exploration.verify_expedition_package(package)
        rules = {"survey": package["survey_board"], "weather": package["weather_board"],
                 "dialogue": package["dialogue_board"], "required_ending": rules["required_ending"]}
    else:
        rules = _object(rules, {"convoy", "contracts", "choice"})
        _require(rules["choice"] in ("relief", "salvage"), "unsupported contract choice")
        board = convoy.validate_convoy_board(rules["convoy"], world)
        initial = convoy.build_convoy(world, board, [])
        validated = contracts.validate_convoy_contracts(rules["contracts"], initial)
        rules = {"convoy": board, "contracts": validated, "choice": rules["choice"]}
    witness = row["witness"]
    _require(type(witness) is list and 1 <= len(witness) <= world["max_ticks"],
             "invalid saga owner witness")
    episode = {"objective": row["objective"], "kind": kind, "source": world,
               "rules": rules, "witness": witness}
    report = replay_episode(episode, witness)
    _require(summarize(episode, report)["gate_satisfied"],
             "saga witness did not earn its required outcome")
    return episode


def replay_episode(episode: dict, actions: Any) -> dict:
    _encode(actions)
    _require(type(actions) is list and len(actions) <= episode["source"]["max_ticks"],
             "invalid local saga ledger")
    world, rules = episode["source"], episode["rules"]
    if episode["kind"] == "survey_expedition":
        report = exploration.build_expedition(
            world, rules["survey"], rules["weather"], rules["dialogue"], actions)
        exploration.verify_expedition(report)
        return report
    if episode["kind"] == "convoy_contract":
        report = convoy.build_convoy(world, rules["convoy"], actions)
        convoy.verify_convoy(report)
        result = contracts.build_convoy_contract_report(
            report, rules["contracts"], choice=rules["choice"])
        contracts.verify_convoy_contract_report(result)
        return result
    raise ValueError("unknown local saga owner")


def summarize(episode: dict, report: dict) -> dict:
    common = {"kind": episode["kind"], "source_digest": digest(episode["source"]),
              "rules_digest": digest(episode["rules"])}
    if episode["kind"] == "survey_expedition":
        status = exploration.expedition_status(report)
        state = report["dialogue"]["bundle"]["state"]
        satisfied = status["complete"] and status["ending"] == episode["rules"]["required_ending"]
        return {**common, "report_digest": report["expedition_digest"],
                "gate_satisfied": bool(satisfied),
                "terminal": state["ending"] is not None or state["tick"] >= episode["source"]["max_ticks"],
                "state": state, "energy": status["energy"], "score": status["score"],
                "required_sites_remaining": status["required_sites_remaining"],
                "delivery_permit": status["delivery_permit"], "next_weather": status["next_weather"],
                "flags": report["dialogue"]["flags"], "trust": report["dialogue"]["trust"],
                "grid": render_map(report).splitlines()}
    status = contracts.convoy_contract_status(report)
    local = report["convoy"]
    tactical = convoy.convoy_status(local)
    state = local["bundle"]["state"]
    return {**common, "report_digest": report["report_digest"],
            "gate_satisfied": status["complete"],
            "terminal": tactical["complete"] or tactical["failed"]
                        or state["ending"] is not None
                        or state["tick"] >= episode["rules"]["convoy"]["max_turns"],
            "state": state, "hull": tactical["hull"], "bounty": tactical["bounty"],
            "waypoint": tactical["waypoint"], "position": tactical["position"],
            "threat": tactical["threat"], "next_waypoint": tactical["next_waypoint"],
            "weapon_charges_spent": tactical["weapon_charges_spent"],
            "tokens": status["tokens"], "required_contracts_remaining": status["remaining"],
            "points": status["points"], "credits": status["credits"],
            "reputation": status["reputation"], "choice": status["choice"]}


def candidate_actions(episode: dict, report: dict, summary: dict) -> list[dict]:
    """Enumerate finite candidates, then ask the actual owner to admit each."""
    if summary["terminal"]:
        return []
    world = episode["source"]
    candidates = [{"op": "move", "direction": direction} for direction in sorted(harbor.DIRECTIONS)]
    candidates += [{"op": "wait"}, {"op": "gather"}, {"op": "deliver"}]
    candidates += [{"op": "craft", "recipe": row["id"]} for row in world["recipes"]]
    candidates += [{"op": "trade", "item": item} for item in sorted(world["npc"]["stock"])]
    if episode["kind"] == "survey_expedition":
        candidates += [{"op": "choose", "choice": c} for c in ("signal", "shelter")]
        for node in episode["rules"]["dialogue"]["nodes"]:
            if node["id"] not in report["dialogue"]["spoken_nodes"]:
                candidates.extend({"op": "talk", "node": node["id"], "choice": choice["id"]}
                                  for choice in node["choices"])
    else:
        candidates += [{"op": name} for name in sorted(convoy.SPECIAL)]
    _require(len(candidates) <= MAX_CANDIDATES, "saga action candidate ceiling exceeded")
    prefix = report["input_actions"] if episode["kind"] == "survey_expedition" else report["convoy"]["actions"]
    legal = []
    for candidate in candidates:
        try:
            replay_episode(episode, [*prefix, candidate])
        except harbor.HarborError:
            continue
        legal.append(candidate)
    return legal
