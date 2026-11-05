"""Choice consequences from earned, independently replayed league contracts.

Relief earns reputation; salvage earns credits. No choice creates core items,
rewrites a completed convoy or bypasses contract prerequisites.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import HarborError, _keys, canonical, digest
from .harbor_crafting_convoy_league import MAX_SAVE_BYTES, verify_league
from .harbor_crafting_convoy_contracts import (
    MAX_BOARD_BYTES as MAX_CONTRACT_BOARD_BYTES,
    build_convoy_contract_report, verify_convoy_contract_report,
)

SCHEMA = "skeleton.game.harbor.convoy-league-consequences.v1"
MAX_CONSEQUENCE_BYTES = MAX_SAVE_BYTES + 8 * (2 * 1024 * 1024) + 65536
FIELDS = {
    "schema", "save", "contract_boards", "choices", "reports",
    "reputation", "credits", "points", "tokens", "complete", "report_digest",
}
CHOICES = {"relief", "salvage"}


def build_league_consequences(save: Any, contract_boards: Any, choices: Any, *,
                              require_all: bool = False) -> dict[str, Any]:
    verify_league(save)
    rounds = save["league"]["rounds"]
    if not isinstance(contract_boards, list) or len(contract_boards) != len(rounds):
        raise HarborError("league consequence board count mismatch")
    if not isinstance(choices, list) or len(choices) != len(save["reports"]):
        raise HarborError("league consequence choices must match played rounds")
    if len(canonical(contract_boards)) > len(rounds) * MAX_CONTRACT_BOARD_BYTES:
        raise HarborError("league consequence boards exceed byte budget")
    if any(type(choice) is not str or choice not in CHOICES for choice in choices):
        raise HarborError("unsupported league consequence choice")
    reports = []
    tokens = []
    reputation = credits = points = 0
    for index, choice in enumerate(choices):
        convoy = save["reports"][index]
        report = build_convoy_contract_report(
            convoy, contract_boards[index], choice=choice, require_all=False,
        )
        verify_convoy_contract_report(report)
        reports.append(report)
        round_id = rounds[index]["id"]
        tokens.extend(round_id + ":" + token for token in report["tokens"])
        points += report["points"]
        reputation += report["reputation"]
        credits += report["credits"]
    complete = bool(save["complete"] and len(reports) == len(rounds)
                    and all(report["complete"] for report in reports))
    if require_all and not complete:
        raise HarborError("league consequence ending not earned")
    result = {
        "schema": SCHEMA, "save": deepcopy(save),
        "contract_boards": deepcopy(contract_boards), "choices": deepcopy(choices),
        "reports": reports, "reputation": reputation, "credits": credits,
        "points": points, "tokens": sorted(tokens), "complete": complete,
    }
    result["report_digest"] = digest(result)
    if len(canonical(result)) > MAX_CONSEQUENCE_BYTES:
        raise HarborError("league consequences exceed byte budget")
    return result


def verify_league_consequences(result: Any, *,
                               require_all: bool = False) -> dict[str, Any]:
    _keys(result, FIELDS, "league consequences")
    if result["schema"] != SCHEMA or len(canonical(result)) > MAX_CONSEQUENCE_BYTES:
        raise HarborError("unsupported or oversized league consequences")
    if result["report_digest"] != digest({
        key: value for key, value in result.items() if key != "report_digest"
    }):
        raise HarborError("league consequence digest mismatch")
    rebuilt = build_league_consequences(
        result["save"], result["contract_boards"], result["choices"],
        require_all=require_all,
    )
    if rebuilt != result:
        raise HarborError("league consequence replay mismatch")
    return {
        "verified": True, "complete": rebuilt["complete"],
        "reputation": rebuilt["reputation"], "credits": rebuilt["credits"],
        "points": rebuilt["points"], "tokens": deepcopy(rebuilt["tokens"]),
        "report_digest": rebuilt["report_digest"],
    }


def compare_league_choices(save: Any, contract_boards: Any) -> dict[str, Any]:
    verify_league(save)
    count = len(save["reports"])
    relief = build_league_consequences(save, contract_boards, ["relief"] * count)
    salvage = build_league_consequences(save, contract_boards, ["salvage"] * count)
    return {
        "relief": {
            "complete": relief["complete"], "reputation": relief["reputation"],
            "credits": relief["credits"], "report_digest": relief["report_digest"],
        },
        "salvage": {
            "complete": salvage["complete"], "reputation": salvage["reputation"],
            "credits": salvage["credits"], "report_digest": salvage["report_digest"],
        },
        "shared_gameplay_digest": save["save_digest"],
    }
