"""One-command first-playable acceptance from authored source to earned endings.

Acceptance is a compact, reproducible receipt: proofs are independently
reconstructed rather than copied as giant nested generated artifacts.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import HarborError, _keys, canonical, digest, validate_source
from .harbor_crafting_convoy import validate_convoy_board, verify_convoy
from .harbor_crafting_convoy_contracts import (
    build_convoy_contract_report, validate_convoy_contracts,
    verify_convoy_contract_report,
)
from .harbor_crafting_convoy_journal import (
    append_convoy_journal, create_convoy_journal, verify_convoy_journal,
)
from .harbor_crafting_convoy_package import (
    build_convoy_package, play_convoy_package, verify_convoy_package_play,
)
from .harbor_crafting_convoy_solver import solve_convoy, verify_convoy_plan

SCHEMA = "skeleton.game.harbor.convoy-acceptance.v1"
MAX_ACCEPT_BYTES = 262144
FIELDS = {
    "schema", "source", "board", "contracts", "actions",
    "plan_digest", "package_digest", "play_digest", "journal_digest",
    "relief_digest", "salvage_digest", "summary", "acceptance_digest",
}


def accept_convoy(source: Any, board: Any, contracts: Any) -> dict[str, Any]:
    world = validate_source(source)
    authored = validate_convoy_board(board, world)
    plan = solve_convoy(world, authored)
    verify_convoy_plan(plan)
    verify_convoy(plan["report"], require_complete=True)
    contract_board = validate_convoy_contracts(contracts, plan["report"])
    package = build_convoy_package("lantern_quay_convoy", world, authored)
    play = play_convoy_package(package, plan["actions"], require_complete=True)
    verify_convoy_package_play(play, require_complete=True)
    if play["report"] != plan["report"]:
        raise HarborError("convoy acceptance package and planner divergence")
    journal = create_convoy_journal(package)
    for index in range(0, len(plan["actions"]), 32):
        journal = append_convoy_journal(
            journal, plan["actions"][index:index + 32],
            expected_digest=journal["journal_digest"],
        )
    status = verify_convoy_journal(journal)
    if not status["complete"] or status["head"] != play["play_digest"]:
        raise HarborError("convoy acceptance journal replay divergence")
    relief = build_convoy_contract_report(
        play["report"], contract_board, choice="relief", require_all=True,
    )
    salvage = build_convoy_contract_report(
        play["report"], contract_board, choice="salvage", require_all=True,
    )
    verify_convoy_contract_report(relief, require_all=True)
    verify_convoy_contract_report(salvage, require_all=True)
    summary = {
        "complete": True,
        "ticks": len(plan["actions"]),
        "hull": play["report"]["state"]["hull"],
        "bounty": play["report"]["state"]["bounty"],
        "contract_points": relief["points"],
        "relief_reputation": relief["reputation"],
        "salvage_credits": salvage["credits"],
        "journal_entries": status["entries"],
    }
    acceptance = {
        "schema": SCHEMA, "source": world, "board": authored,
        "contracts": contract_board, "actions": deepcopy(plan["actions"]),
        "plan_digest": plan["plan_digest"],
        "package_digest": package["package_digest"],
        "play_digest": play["play_digest"],
        "journal_digest": journal["journal_digest"],
        "relief_digest": relief["report_digest"],
        "salvage_digest": salvage["report_digest"],
        "summary": summary,
    }
    acceptance["acceptance_digest"] = digest(acceptance)
    if len(canonical(acceptance)) > MAX_ACCEPT_BYTES:
        raise HarborError("convoy acceptance receipt exceeds byte budget")
    return acceptance


def verify_convoy_acceptance(acceptance: Any) -> dict[str, Any]:
    _keys(acceptance, FIELDS, "convoy acceptance")
    if acceptance["schema"] != SCHEMA or len(canonical(acceptance)) > MAX_ACCEPT_BYTES:
        raise HarborError("unsupported or oversized convoy acceptance")
    if acceptance["acceptance_digest"] != digest({
        k: v for k, v in acceptance.items() if k != "acceptance_digest"
    }):
        raise HarborError("convoy acceptance digest mismatch")
    rebuilt = accept_convoy(
        acceptance["source"], acceptance["board"], acceptance["contracts"],
    )
    if rebuilt != acceptance:
        raise HarborError("convoy acceptance source-to-runtime replay mismatch")
    return {
        "verified": True, **deepcopy(rebuilt["summary"]),
        "acceptance_digest": rebuilt["acceptance_digest"],
    }
