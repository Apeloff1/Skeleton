"""Executable source-to-runtime acceptance matrix for the Cinder Ridge game stack.

This is a focused product acceptance runner, not a substitute for CI, security
review, device tests or release qualification. Each contract is actually
executed; failures remain visible and make the aggregate fail closed.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from .custody import digest, verify_run
from .schema import parse_world, world_dict
from .engine import initial_state
from .journal import open_journal, append_journal, verify_journal, export_journal
from .package import build_package, verify_package, play_package
from .routebook import run_route, export_route, verify_route_export
from .workbench import open_workbench, edit_workbench, preview_workbench, verify_workbench_export, export_workbench
from .tactics import suggest, advance
from .campaign_acceptance import run_acceptance as campaign_acceptance
from .campaign import verify_export as verify_campaign_export
from .missions import parse_missions, evaluate_missions
from .acceptance import acceptance_actions

HERE = Path(__file__).resolve().parent
CONTRACT = "ridge.rescue.acceptance.matrix.v1"


class AcceptanceMatrixError(ValueError):
    pass


def _fixture(name: str, limit: int = 160_000) -> bytes:
    from .io import read_bounded
    return read_bounded(HERE / name, limit)


def _world_contract() -> dict:
    world = parse_world(_fixture("cinder_ridge.json"))
    package = build_package(world)
    verified = verify_package(package)
    if world_dict(verified["world"]) != world_dict(world):
        raise AcceptanceMatrixError("world package source mismatch")
    journal = open_journal(world)
    if verify_journal(journal)["state"] != initial_state(world):
        raise AcceptanceMatrixError("initial world journal mismatch")
    replay = play_package(package, [])
    if verify_run(replay)["state"] != initial_state(world):
        raise AcceptanceMatrixError("packaged gameplay replay mismatch")
    return {"source_sha256": digest(world_dict(world)), "package_sha256": package["sha256"],
            "status": "verified-in-process", "world": world.name}


def _routes_contract() -> dict:
    source = _fixture("cinder_ridge_routebook.json")
    results = {}
    for track, expected in (("protect-route", "won:protect"), ("salvage-route", "won:salvage")):
        session = run_route(source, track)
        checked = verify_route_export(export_route(session))
        if checked["status"] != "completed" or checked["state"]["status"] != expected:
            raise AcceptanceMatrixError("route did not earn declared ending")
        results[track] = {"head": checked["head"], "ending": expected, "turns": checked["state"]["turn"]}
    return {"status": "verified-in-process", "routes": results}


def _campaign_contract() -> dict:
    bundle = campaign_acceptance()
    checked = verify_campaign_export(bundle)
    if checked["status"] != "completed" or checked["index"] != 2:
        raise AcceptanceMatrixError("two-chapter campaign incomplete")
    return {"status": "verified-in-process", "head": checked["head"], "episodes": checked["index"]}


def _workbench_contract() -> dict:
    source = _fixture("cinder_ridge_acceptance.json")
    session = open_workbench(source)
    updated = edit_workbench(session, {"kind": "rename", "target": "world",
                                      "value": "Cinder Ridge Acceptance Workbench"}, expected_head=session["head"])
    checked = verify_workbench_export(export_workbench(updated))
    if checked["revision_sha256"] == checked["origin_sha256"]:
        raise AcceptanceMatrixError("workbench revision did not change source")
    preview = preview_workbench(updated, acceptance_actions("protect"))
    if preview["status"] != "won:protect":
        raise AcceptanceMatrixError("edited world not playable")
    return {"status": "verified-in-process", "revision_sha256": checked["revision_sha256"],
            "ending": preview["status"]}


def _tactics_contract() -> dict:
    world = parse_world(_fixture("cinder_ridge_acceptance.json"))
    rules = _fixture("cinder_ridge_tactics.json", 16_384)
    journal = open_journal(world)
    advice = suggest(world, journal, rules)
    if not advice["ranked"] or advice["guaranteed"]:
        raise AcceptanceMatrixError("tactics preview missing or falsely guaranteed")
    committed = advance(world, journal, rules, expected_head=journal["head"])
    verified = verify_journal(committed["journal"])
    if verified["state"]["turn"] != 1 or verified["actions"] != [committed["action"]]:
        raise AcceptanceMatrixError("tactics action not committed canonically")
    if verify_run(export_journal(committed["journal"]))["state"] != verified["state"]:
        raise AcceptanceMatrixError("tactics replay export mismatch")
    return {"status": "verified-in-process", "action": committed["action"],
            "head": verified["head"]}


def _missions_contract() -> dict:
    from .campaign_acceptance import LAST_SIGNAL
    source = _fixture("cinder_ridge_missions.json")
    parsed = parse_missions(source)
    world = parse_world(parsed["world"])
    journal = open_journal(world)
    for action in LAST_SIGNAL:
        journal = append_journal(journal, action, expected_head=journal["head"])
    checked = verify_journal(journal)
    if checked["state"]["status"] != "won:salvage":
        raise AcceptanceMatrixError("mission path did not earn salvage ending")
    report = evaluate_missions(parsed, journal)
    if not any(node["id"] == "salvage_exit" and node["earned"] for node in report["earned"]):
        raise AcceptanceMatrixError("mission objective not earned")
    return {"status": "verified-in-process", "mission_score": report["score"],
            "ending": checked["state"]["status"], "journal_head": checked["head"]}



def _challenges_contract() -> dict:
    from .challenges import list_challenges, play_challenge
    catalog = list_challenges()
    if catalog["count"] != 8:
        raise AcceptanceMatrixError("original challenge catalog incomplete")
    outcomes = {}
    for entry in catalog["challenges"]:
        bundle = play_challenge(entry["id"])
        state = verify_run(bundle)["state"]
        if state["status"] != "won:" + entry["ending"]:
            raise AcceptanceMatrixError("original challenge ending mismatch")
        outcomes[entry["id"]] = {"ending": state["status"], "turns": state["turn"]}
    return {"status": "verified-in-process", "count": len(outcomes), "outcomes": outcomes}


def _league_contract() -> dict:
    from .league_acceptance import run_acceptance as league_acceptance
    from .league import verify_league_export
    checked = verify_league_export(league_acceptance())
    if checked["entries"] != 2 or checked["champion"] != "ridge-protectors":
        raise AcceptanceMatrixError("league standings not earned")
    return {"status": "verified-in-process", "entries": checked["entries"],
            "champion": checked["champion"], "head": checked["head"]}


def _consumer_contract() -> dict:
    from .consumer_acceptance import run_acceptance
    report = run_acceptance()
    if report["status"] != "verified-in-process" or report["chapters"] != 2:
        raise AcceptanceMatrixError("consumer save/restart/export acceptance failed")
    if not report["portable_export_verified"] or report["restart_count"] != report["actions"]:
        raise AcceptanceMatrixError("consumer restart or export did not replay")
    return {"status": "verified-in-process", "chapters": report["chapters"],
            "actions": report["actions"], "head": report["head"]}


def _consumer_process_contract() -> dict:
    """Actually launch source and standalone game across separate processes."""
    from .consumer_smoke import run_smoke, run_portable_smoke
    source = run_smoke()
    portable = run_portable_smoke()
    for report in (source, portable):
        if (report["result"] != "passed-on-current-host" or
            not report["portable_export_verified"] or
            not report["portable_restore_audited"] or
            not report["restore_overwrite_rejected"] or
            not report["tampered_restore_rejected"] or
            not report["invalid_mutation_rejected"] or
            not report["real_processes"] or
            report["windows_device_certified"] or report["release_certified"]):
            raise AcceptanceMatrixError("consumer cross-process custody contract failed")
    if not portable["portable_zipapp_verified"] or portable["source_checkout_dependency"]:
        raise AcceptanceMatrixError("standalone game still depends on source checkout")
    if portable["earned_head"] != source["earned_head"]:
        raise AcceptanceMatrixError("source and standalone earned outcomes diverged")
    return {"status": "verified-in-process", "earned_head": source["earned_head"],
            "source_actions": source["actions"], "portable_actions": portable["actions"],
            "portable_sha256": portable["archive_sha256"], "restore_verified": True,
            "device_certified": False, "release_certified": False}


def run_matrix(*, fail_fast: bool = False) -> dict:
    if type(fail_fast) is not bool:
        raise AcceptanceMatrixError("invalid fail_fast")
    checks: tuple[tuple[str, Callable[[], dict]], ...] = (
        ("world-package", _world_contract),
        ("routebook-choices", _routes_contract),
        ("two-chapter-campaign", _campaign_contract),
        ("workbench-editor", _workbench_contract),
        ("tactics-journal", _tactics_contract),
        ("mission-events", _missions_contract),
        ("original-challenges", _challenges_contract),
        ("earned-league", _league_contract),
        ("consumer-restart-export", _consumer_contract),
        ("consumer-portable-restart-restore", _consumer_process_contract),
    )
    reports = {}
    for name, check in checks:
        try:
            reports[name] = check()
        except (ValueError, TypeError, KeyError, OSError, AssertionError) as exc:
            reports[name] = {"status": "failed", "error": type(exc).__name__, "reason": str(exc)[:256]}
            if fail_fast:
                break
    success = len(reports) == len(checks) and all(
        item["status"] == "verified-in-process" for item in reports.values())
    return {"schema": CONTRACT, "passed": success, "completed_checks": len(reports),
            "expected_checks": len(checks), "checks": reports,
            "release_certified": False, "device_certified": False,
            "ci_certified": False}
