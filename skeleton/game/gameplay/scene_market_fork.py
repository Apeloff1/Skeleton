"""Replay-proven alternative futures for a player-authored scene market.

Previewing choices never spends currency or mutates the player's checkpoint.
Every accepted branch is reduced by the canonical market engine; a blocked
choice remains explicitly blocked rather than silently producing a fake win.
Witness checksums are integrity hints, not cryptographic authentication.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_market import (
    _action, _advance, _bounded, _json, original_market, simulate_market,
    verify_market,
)
from skeleton.game.gameplay.scene_tile_walk import MAX_STEPS, _action as tile_action
from skeleton.game.gameplay.scene_travel import SceneTravelError, _id, _object

SCHEMA = "skeleton.scene_market_fork.v1"
BUNDLE = "skeleton.scene_market_fork_bundle.v1"
MAX_CANDIDATES = 12
MAX_ACTIONS = 24
MAX_TOTAL_ACTIONS = 96
MAX_INPUT_BYTES = 128 * 1024


def _normalize_action(raw: Any) -> dict[str, Any]:
    """Validate both market and nested tile command schemas before preview."""
    action = _action(raw)
    if action["kind"] == "tile":
        return {"kind": "tile", "action": tile_action(action["action"])}
    return action


def normalize_candidates(raw: Any, *, remaining: int) -> list[dict[str, Any]]:
    """Reject excessive or ambiguous plans before evaluating a single move."""
    _bounded(raw, MAX_INPUT_BYTES)
    if type(raw) is not list or not 1 <= len(raw) <= MAX_CANDIDATES:
        raise SceneTravelError("invalid fork candidate count")
    if type(remaining) is not int or remaining < 0 or remaining > MAX_STEPS:
        raise SceneTravelError("invalid remaining market turn budget")
    names: set[str] = set()
    normalized: list[dict[str, Any]] = []
    total = 0
    for raw_candidate in raw:
        item = _object(raw_candidate, {"candidate_id", "actions"}, "market fork candidate")
        name = _id(item["candidate_id"], "fork candidate id")
        if name in names:
            raise SceneTravelError("duplicate fork candidate id")
        names.add(name)
        actions = item["actions"]
        if type(actions) is not list or not 1 <= len(actions) <= MAX_ACTIONS:
            raise SceneTravelError("invalid fork action count")
        total += len(actions)
        if total > MAX_TOTAL_ACTIONS:
            raise SceneTravelError("fork action budget exceeded")
        # Validate shape even for branches that later encounter a legal move
        # rejection; invalid schemas are never silently counted as gameplay.
        normalized.append({
            "candidate_id": name,
            "actions": [_normalize_action(action) for action in actions],
        })
    return sorted(normalized, key=lambda item: item["candidate_id"])


def _evaluate(checkpoint: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    outcomes: list[dict[str, Any]] = []
    for candidate in candidates:
        state = checkpoint
        blocked_step: int | None = None
        blocked_reason: str | None = None
        for index, action in enumerate(candidate["actions"]):
            try:
                state = _advance(state, action)
            except SceneTravelError as exc:
                blocked_step = index
                blocked_reason = str(exc)
                break
        if blocked_step is not None:
            outcomes.append({
                "candidate_id": candidate["candidate_id"], "status": "blocked",
                "blocked_step": blocked_step, "blocked_reason": blocked_reason,
                "state_digest": None, "phase": None, "tick": None,
                "credits": None, "reputation": None, "delivered": None,
            })
        else:
            s = state["state"]
            outcomes.append({
                "candidate_id": candidate["candidate_id"], "status": "accepted",
                "blocked_step": None, "blocked_reason": None,
                "state_digest": state["state_digest"], "phase": s["phase"],
                "tick": s["tick"], "credits": s["credits"],
                "reputation": s["reputation"], "delivered": list(s["delivered"]),
            })
    return {"outcomes": outcomes, "heuristic_candidate": _heuristic(outcomes)}


def _heuristic(outcomes: list[dict[str, Any]]) -> str | None:
    """Rank only successfully replayed alternatives; no optimality claim."""
    accepted = [item for item in outcomes if item["status"] == "accepted"]
    if not accepted:
        return None
    phase_rank = {"won": 3, "active": 2, "draw": 1, "lost": 0}
    return min(accepted, key=lambda item: (
        -phase_rank.get(item["phase"], 0), -len(item["delivered"]),
        -item["reputation"], -item["credits"], item["tick"],
        item["candidate_id"],
    ))["candidate_id"]


def evaluate_market_fork(checkpoint: Any, candidates: Any) -> dict[str, Any]:
    """Return a portable preview of independently replayed future choices."""
    canonical = verify_market(checkpoint)
    plans = normalize_candidates(
        candidates, remaining=MAX_STEPS - len(canonical["journal"]),
    )
    result = {
        "schema_version": SCHEMA,
        "checkpoint": canonical,
        "source_digest": canonical["source_digest"],
        "checkpoint_state_digest": canonical["state_digest"],
        "candidates": plans,
        **_evaluate(canonical, plans),
        "qualification": "offline_replay_preview_not_global_optimum",
    }
    result["checksum"] = dig(result)
    _bounded(result)
    return result


def verify_market_fork(payload: Any) -> dict[str, Any]:
    """Rebuild every claimed future from its immutable source-bound checkpoint."""
    _bounded(payload)
    obj = _object(payload, {
        "schema_version", "checkpoint", "source_digest",
        "checkpoint_state_digest", "candidates", "outcomes",
        "heuristic_candidate", "qualification", "checksum",
    }, "market fork report")
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported market fork report")
    if obj["qualification"] != "offline_replay_preview_not_global_optimum":
        raise SceneTravelError("fork preview qualification mismatch")
    expected = evaluate_market_fork(obj["checkpoint"], obj["candidates"])
    if obj != expected:
        raise SceneTravelError("market fork replay or witness mismatch")
    return expected


def choose_market_fork(report: Any, candidate_id: str) -> dict[str, Any]:
    """Commit exactly one validated future, yielding a normal market save."""
    canonical = verify_market_fork(report)
    name = _id(candidate_id, "selected fork candidate")
    result = next((item for item in canonical["outcomes"]
                   if item["candidate_id"] == name), None)
    if result is None:
        raise SceneTravelError("unknown fork candidate")
    if result["status"] != "accepted":
        raise SceneTravelError("blocked fork cannot be committed")
    actions = next(item["actions"] for item in canonical["candidates"]
                   if item["candidate_id"] == name)
    state = canonical["checkpoint"]
    for action in actions:
        state = _advance(state, action)
    if state["state_digest"] != result["state_digest"]:
        raise SceneTravelError("selected fork replay drift")
    return verify_market(state)


def export_market_fork(report: Any) -> dict[str, Any]:
    canonical = verify_market_fork(report)
    bundle = {
        "schema_version": BUNDLE,
        "source_digest": canonical["source_digest"],
        "checkpoint_state_digest": canonical["checkpoint_state_digest"],
        "report": canonical,
    }
    bundle["checksum"] = dig(bundle)
    _bounded(bundle)
    return bundle


def import_market_fork(bundle: Any) -> dict[str, Any]:
    _bounded(bundle)
    obj = _object(bundle, {
        "schema_version", "source_digest", "checkpoint_state_digest",
        "report", "checksum",
    }, "market fork bundle")
    if obj["schema_version"] != BUNDLE:
        raise SceneTravelError("unsupported fork bundle")
    if obj["checksum"] != dig({key: value for key, value in obj.items()
                               if key != "checksum"}):
        raise SceneTravelError("fork bundle checksum mismatch")
    report = verify_market_fork(obj["report"])
    if (obj["source_digest"] != report["source_digest"]
            or obj["checkpoint_state_digest"] != report["checkpoint_state_digest"]):
        raise SceneTravelError("fork bundle lineage mismatch")
    return report


def original_fork() -> dict[str, Any]:
    source, actions = original_market()
    checkpoint = simulate_market(source, [])
    return evaluate_market_fork(checkpoint, [
        {"candidate_id": "complete_delivery", "actions": actions},
        {"candidate_id": "unearned_purchase",
         "actions": [{"kind": "buy", "offer_id": "copper_badge"}]},
    ])


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-market-fork")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    evaluate = sub.add_parser("evaluate")
    evaluate.add_argument("--session-json", required=True)
    evaluate.add_argument("--candidates-json", required=True)
    for name in ("verify", "export", "choose"):
        command = sub.add_parser(name)
        command.add_argument("--report-json", required=True)
        if name == "choose":
            command.add_argument("--candidate-id", required=True)
    sub.add_parser("import").add_argument("--bundle-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = original_fork()
        elif args.command == "evaluate":
            result = evaluate_market_fork(
                _json(args.session_json), _json(args.candidates_json),
            )
        elif args.command == "import":
            result = import_market_fork(_json(args.bundle_json))
        else:
            report = _json(args.report_json)
            if args.command == "verify":
                result = verify_market_fork(report)
            elif args.command == "export":
                result = export_market_fork(report)
            else:
                result = choose_market_fork(report, args.candidate_id)
        _bounded(result)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (SceneTravelError, ValueError, TypeError, KeyError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
