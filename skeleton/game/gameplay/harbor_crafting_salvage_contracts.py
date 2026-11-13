"""Source-bound salvage mission objectives, earned events and choice consequences.

Contracts observe verified canonical and salvage state. They cannot mint currency,
inventory, achievements or endings; scores are only awarded from actual replay.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import (
    HarborError, _identifier, _integer, _keys, canonical, digest,
    initial_state, normalize_action, step,
)
from .harbor_crafting_salvage import (
    MAX_BOARD_BYTES, MAX_REPORT_BYTES, SPECIAL, _transition,
    initial_salvage_state, normalize_salvage_action, verify_salvage,
)

SCHEMA = "skeleton.game.harbor.salvage-contract-board.v1"
REPORT_SCHEMA = "skeleton.game.harbor.salvage-contract-report.v1"
MAX_CONTRACTS = 16
MAX_CONTRACT_BOARD_BYTES = MAX_BOARD_BYTES
MAX_CONTRACT_REPORT_BYTES = MAX_REPORT_BYTES * 2
BOARD_KEYS = {"schema", "source_id", "objectives"}
OBJECTIVE_KEYS = {"id", "kind", "target", "points"}
REPORT_KEYS = {"schema", "report", "board", "events", "earned",
               "score", "board_digest", "contract_digest"}
KINDS = {"recover", "secure", "hull", "reward", "complete"}


def validate_salvage_contracts(board: Any, report: Any) -> dict[str, Any]:
    verify_salvage(report)
    _keys(board, BOARD_KEYS, "salvage contract board")
    if board["schema"] != SCHEMA or board["source_id"] != report["source"]["id"]:
        raise HarborError("salvage contract source mismatch")
    if len(canonical(board)) > MAX_CONTRACT_BOARD_BYTES:
        raise HarborError("salvage contract board oversized")
    objectives = board["objectives"]
    if not isinstance(objectives, list) or not 1 <= len(objectives) <= MAX_CONTRACTS:
        raise HarborError("invalid salvage contract count")
    names: set[str] = set()
    sites = {site["id"] for site in report["board"]["sites"]}
    for objective in objectives:
        _keys(objective, OBJECTIVE_KEYS, "salvage contract")
        name = _identifier(objective["id"], "salvage contract id")
        if name in names:
            raise HarborError("duplicate salvage contract id")
        names.add(name)
        kind = objective["kind"]
        if type(kind) is not str or kind not in KINDS:
            raise HarborError("invalid salvage contract kind")
        _integer(objective["points"], 1, 100, "salvage contract points")
        target = objective["target"]
        if kind in {"recover", "secure"}:
            if type(target) is not str or target not in sites:
                raise HarborError("salvage contract references unknown site")
        elif kind == "hull":
            _integer(target, 1, report["board"]["hull"], "salvage contract hull")
        elif kind == "reward":
            _integer(target, 1, 1600, "salvage contract reward")
        elif target is not None:
            raise HarborError("salvage completion contract target must be null")
    return deepcopy(board)


def _earned(objective: dict[str, Any], overlay: dict[str, Any]) -> bool:
    kind = objective["kind"]
    target = objective["target"]
    if kind == "recover":
        return target in overlay["cargo"] or target in overlay["secured"]
    if kind == "secure":
        return target in overlay["secured"]
    if kind == "hull":
        return overlay["hull"] >= target and overlay["tick"] > 0
    if kind == "reward":
        return overlay["reward"] >= target
    return overlay["complete"]


def build_salvage_contract_report(report: Any, board: Any, *,
                                  require_all: bool = False) -> dict[str, Any]:
    verify_salvage(report)
    authored = validate_salvage_contracts(board, report)
    source = report["source"]
    salvage_board = report["board"]
    state = initial_state(source)
    overlay = initial_salvage_state(salvage_board)
    events: list[dict[str, Any]] = []
    earned: list[str] = []
    previous = digest({"report": report["report_digest"],
                       "board": digest(authored), "genesis": True})
    for index, raw in enumerate(report["actions"]):
        action = normalize_salvage_action(raw)
        core = ({"op": "choose", "choice": "signal"} if action["op"] == "rescue"
                else {"op": "wait"} if action["op"] in SPECIAL else action)
        updated_world = step(source, state, core)
        updated = _transition(source, salvage_board, overlay, state, updated_world, action)
        newly = [o["id"] for o in authored["objectives"]
                 if o["id"] not in earned and _earned(o, updated)]
        if newly:
            event = {"tick": index + 1, "objectives": newly, "previous": previous}
            event["digest"] = digest(event)
            events.append(event)
            previous = event["digest"]
            earned.extend(newly)
        state, overlay = updated_world, updated
    if state != report["bundle"]["state"] or overlay != report["state"]:
        raise HarborError("salvage contract replay diverged")
    if require_all and len(earned) != len(authored["objectives"]):
        raise HarborError("salvage contract objectives not earned")
    score = sum(o["points"] for o in authored["objectives"] if o["id"] in earned)
    result = {"schema": REPORT_SCHEMA, "report": deepcopy(report), "board": authored,
              "events": events, "earned": earned, "score": score,
              "board_digest": digest(authored)}
    result["contract_digest"] = digest(result)
    if len(canonical(result)) > MAX_CONTRACT_REPORT_BYTES:
        raise HarborError("salvage contract report exceeds byte budget")
    return result


def verify_salvage_contract_report(value: Any, *,
                                   require_all: bool = False) -> dict[str, Any]:
    _keys(value, REPORT_KEYS, "salvage contract report")
    if value["schema"] != REPORT_SCHEMA or len(canonical(value)) > MAX_CONTRACT_REPORT_BYTES:
        raise HarborError("unsupported or oversized salvage contract report")
    if value["contract_digest"] != digest({k: v for k, v in value.items()
                                            if k != "contract_digest"}):
        raise HarborError("salvage contract report digest mismatch")
    rebuilt = build_salvage_contract_report(value["report"], value["board"],
                                            require_all=require_all)
    if rebuilt != value:
        raise HarborError("salvage contract replay mismatch")
    return {"earned": list(value["earned"]), "score": value["score"],
            "contract_digest": value["contract_digest"]}
