"""Recover source-bound local packages and canonical convoy solver into saga authoring."""
from __future__ import annotations

from typing import Any

from skeleton.app.gameforge_campaign import detached, digest
from skeleton.app.gameforge_saga import MAX_EPISODES, REQUEST_SCHEMA, build_saga, play_saga
from skeleton.app.original_quest_cli import _encode, _object, _require, _text
from skeleton.game.gameplay import harbor_crafting as harbor
from skeleton.game.gameplay import harbor_crafting_expedition as exploration
from skeleton.game.gameplay.harbor_crafting_convoy_solver import solve_convoy, verify_convoy_plan
from skeleton.gameforge.errors import GameForgeError

SCHEMA = "skeleton.gameforge.saga.author.v1"
RECEIPT_SCHEMA = "skeleton.gameforge.saga.author.receipt.v1"


def author_saga(source: Any) -> dict:
    data = _object(detached(source), {"schema", "expedition", "bindings"})
    _require(data["schema"] == SCHEMA, "unsupported saga author schema")
    _require(type(data["bindings"]) is list and 1 <= len(data["bindings"]) <= MAX_EPISODES,
             "invalid saga author binding count")
    episodes = []
    custody = []
    seen = set()
    for raw in data["bindings"]:
        item = _object(raw, {"objective", "kind", "source", "rules"}, {"witness", "package"})
        objective = _text(item["objective"], 128)
        _require(objective not in seen, "duplicate saga author objective")
        seen.add(objective)
        world = harbor.validate_source(item["source"])
        kind = _text(item["kind"], 32)
        if kind == "survey_expedition":
            rules = _object(item["rules"], {"survey", "weather", "dialogue", "required_ending"})
            package = exploration.build_expedition_package(
                world["id"], world, rules["survey"], rules["weather"], rules["dialogue"])
            if "package" in item:
                submitted = item["package"]
                exploration.verify_expedition_package(submitted)
                _require(_encode(package) == _encode(submitted), "survey package independent source mismatch")
            _require("witness" in item, "survey author requires explicit legal witness")
            witness = item["witness"]
            receipt = {"owner": "harbor_crafting_expedition",
                       "package_digest": package["package_digest"],
                       "witness_origin": "authored"}
        elif kind == "convoy_contract":
            rules = _object(item["rules"], {"convoy", "contracts", "choice"})
            _require("package" not in item, "unsupported convoy package input")
            if "witness" in item:
                witness = item["witness"]
                receipt = {"owner": "harbor_crafting_convoy", "witness_origin": "authored"}
            else:
                solved = solve_convoy(world, rules["convoy"])
                proof = verify_convoy_plan(solved)
                _require(proof["complete"], "canonical convoy solver did not complete")
                witness = solved["actions"]
                receipt = {"owner": "harbor_crafting_convoy_solver",
                           "solver_digest": solved["plan_digest"], "witness_origin": "canonical_solver"}
        else:
            raise ValueError("unknown saga author owner")
        episodes.append({"objective": objective, "kind": kind, "source": world,
                         "rules": rules, "witness": witness})
        custody.append({"objective": objective, "source_digest": digest(world),
                        "rules_digest": digest(rules), **receipt})
    request = {"schema": REQUEST_SCHEMA, "expedition": data["expedition"], "episodes": episodes}
    design = build_saga(request)
    genesis = play_saga(request, [])
    _require(genesis["actions"] == [] and genesis["state"]["earned_rewards"] == []
             and all(ep["state"]["tick"] == 0 for ep in genesis["state"]["episodes"].values()),
             "saga authoring cannot confer played progress")
    body = {"schema": RECEIPT_SCHEMA, "source_digest": digest(data),
            "request": request, "design_digest": design["design_digest"],
            "genesis_digest": genesis["session_digest"], "owner_custody": custody,
            "native_qualified": False, "release_qualified": False}
    result = {**body, "author_digest": digest(body)}
    _encode({"request": source, "composition": result})
    return result


def verify_authoring(source: Any, submitted: Any) -> bool:
    try:
        return _encode(submitted) == _encode(author_saga(source))
    except (GameForgeError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
        return False
