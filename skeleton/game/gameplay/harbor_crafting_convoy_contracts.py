"""Earned convoy contract chain and mutually exclusive relief/salvage consequences.

Contracts are derived exclusively from independently replayed movement, crafting,
escort and combat. No client-supplied reward or completion flag is authoritative.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import HarborError, _identifier, _integer, _keys, canonical, digest
from .harbor_crafting_convoy import verify_convoy

BOARD_SCHEMA = "skeleton.game.harbor.convoy-contracts.v1"
REPORT_SCHEMA = "skeleton.game.harbor.convoy-contract-report.v1"
MAX_BOARD_BYTES = 32768
MAX_REPORT_BYTES = 2 * 1024 * 1024
MAX_CONTRACTS = 16
KINDS = {"visit", "craft", "defeat", "hull", "bounty", "complete"}
BOARD_FIELDS = {"schema", "source_id", "contracts"}
CONTRACT_FIELDS = {"id", "kind", "target", "requires", "points", "required", "token"}
REPORT_FIELDS = {
    "schema", "convoy", "board", "choice", "awards", "tokens",
    "points", "credits", "reputation", "complete", "report_digest",
}


def validate_convoy_contracts(board: Any, convoy: Any) -> dict[str, Any]:
    verify_convoy(convoy)
    _keys(board, BOARD_FIELDS, "convoy contract board")
    if (board["schema"] != BOARD_SCHEMA
            or board["source_id"] != convoy["source"]["id"]
            or len(canonical(board)) > MAX_BOARD_BYTES):
        raise HarborError("convoy contract source/schema/size mismatch")
    contracts = board["contracts"]
    if not isinstance(contracts, list) or not 1 <= len(contracts) <= MAX_CONTRACTS:
        raise HarborError("invalid convoy contract count")
    encounters = {e["id"] for e in convoy["board"]["encounters"]}
    craftable = {
        item for recipe in convoy["source"]["recipes"] for item in recipe["output"]
    }
    seen: set[str] = set()
    tokens: set[str] = set()
    required = 0
    for contract in contracts:
        _keys(contract, CONTRACT_FIELDS, "convoy contract")
        name = _identifier(contract["id"], "contract id")
        kind = contract["kind"]
        if type(kind) is not str or kind not in KINDS:
            raise HarborError("unsupported convoy contract kind")
        target = _identifier(contract["target"], "contract target")
        if name in seen:
            raise HarborError("duplicate convoy contract")
        requires = contract["requires"]
        if (not isinstance(requires, list) or len(requires) > MAX_CONTRACTS
                or any(type(item) is not str or item not in seen for item in requires)
                or len(set(requires)) != len(requires)):
            raise HarborError("invalid or cyclic convoy contract prerequisites")
        if kind == "visit":
            if not target.isdecimal() or str(int(target)) != target or not 1 <= int(target) < len(convoy["board"]["route"]):
                raise HarborError("invalid convoy contract waypoint")
        elif kind == "craft":
            if target not in craftable:
                raise HarborError("unknown convoy contract craft")
        elif kind == "defeat":
            if target not in encounters:
                raise HarborError("unknown convoy contract enemy")
        elif kind == "complete":
            if target != "dock":
                raise HarborError("invalid convoy completion target")
        else:
            if not target.isdecimal() or str(int(target)) != target:
                raise HarborError("invalid convoy contract threshold")
            _integer(int(target), 0, 100, "convoy contract threshold")
        _integer(contract["points"], 0, 100, "convoy contract points")
        if type(contract["required"]) is not bool:
            raise HarborError("invalid convoy contract required flag")
        token = _identifier(contract["token"], "convoy contract token")
        if token in tokens:
            raise HarborError("duplicate convoy contract token")
        tokens.add(token)
        seen.add(name)
        required += contract["required"]
    if not required:
        raise HarborError("convoy contracts need a required objective")
    return deepcopy(board)


def _earned(convoy: dict[str, Any], kind: str, target: str) -> bool:
    state = convoy["state"]
    if kind == "visit":
        return state["index"] >= int(target)
    if kind == "craft":
        recipes = {
            recipe["id"]: set(recipe["output"])
            for recipe in convoy["source"]["recipes"]
        }
        return any(
            a["op"] == "craft" and target in recipes[a["recipe"]]
            for a in convoy["actions"] if a["op"] == "craft"
        )
    if kind == "defeat":
        encounter = next(e for e in convoy["board"]["encounters"] if e["id"] == target)
        index = encounter["at_index"]
        return (state["index"] > index
                or (state["index"] == index and state["threat"] is None))
    if kind == "hull":
        return state["hull"] >= int(target) and not state["failed"]
    if kind == "bounty":
        return state["bounty"] >= int(target)
    return state["complete"]


def build_convoy_contract_report(convoy: Any, board: Any, *,
                                 choice: str = "relief",
                                 require_all: bool = False) -> dict[str, Any]:
    verify_convoy(convoy)
    authored = validate_convoy_contracts(board, convoy)
    if type(choice) is not str or choice not in {"relief", "salvage"}:
        raise HarborError("unsupported convoy consequence")
    awarded: set[str] = set()
    tokens: list[str] = []
    awards: list[dict[str, Any]] = []
    points = 0
    for contract in authored["contracts"]:
        if (all(name in awarded for name in contract["requires"])
                and _earned(convoy, contract["kind"], contract["target"])):
            awarded.add(contract["id"])
            tokens.append(contract["token"])
            points += contract["points"]
            awards.append({
                "id": contract["id"], "token": contract["token"],
                "points": contract["points"],
            })
    required = all(
        not contract["required"] or contract["id"] in awarded
        for contract in authored["contracts"]
    )
    state = convoy["state"]
    eligible = state["hull"] >= 2 if choice == "relief" else state["bounty"] >= 7
    complete = state["complete"] and required and eligible
    if require_all and not complete:
        raise HarborError("convoy contract ending not earned")
    report = {
        "schema": REPORT_SCHEMA, "convoy": deepcopy(convoy),
        "board": authored, "choice": choice, "awards": awards,
        "tokens": sorted(tokens), "points": points,
        "credits": points + state["bounty"] if complete and choice == "salvage" else 0,
        "reputation": points + state["hull"] if complete and choice == "relief" else 0,
        "complete": complete,
    }
    report["report_digest"] = digest(report)
    if len(canonical(report)) > MAX_REPORT_BYTES:
        raise HarborError("convoy contract report exceeds byte budget")
    return report


def verify_convoy_contract_report(report: Any, *,
                                  require_all: bool = False) -> dict[str, Any]:
    _keys(report, REPORT_FIELDS, "convoy contract report")
    if report["schema"] != REPORT_SCHEMA or len(canonical(report)) > MAX_REPORT_BYTES:
        raise HarborError("unsupported or oversized convoy contract report")
    if report["report_digest"] != digest({
        key: value for key, value in report.items() if key != "report_digest"
    }):
        raise HarborError("convoy contract digest mismatch")
    rebuilt = build_convoy_contract_report(
        report["convoy"], report["board"], choice=report["choice"],
        require_all=require_all,
    )
    if rebuilt != report:
        raise HarborError("convoy contract replay mismatch")
    return {
        "complete": rebuilt["complete"], "choice": rebuilt["choice"],
        "points": rebuilt["points"], "credits": rebuilt["credits"],
        "reputation": rebuilt["reputation"], "awards": len(rebuilt["awards"]),
        "report_digest": rebuilt["report_digest"],
    }


def convoy_contract_status(report: Any) -> dict[str, Any]:
    status = verify_convoy_contract_report(report)
    earned = {entry["id"] for entry in report["awards"]}
    return {
        **status, "tokens": deepcopy(report["tokens"]),
        "remaining": [
            c["id"] for c in report["board"]["contracts"]
            if c["required"] and c["id"] not in earned
        ],
    }
