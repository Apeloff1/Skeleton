"""Replay-verified branching checkpoints for canonical offline mission gameplay.

No rewards, choices or endings are granted by this editor. Every saved head is
replayed by the authored mission runtime. Hashes detect corruption, not authors.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_travel import SceneTravelError, _id, _object
from skeleton.game.gameplay.scene_mission import (
    _action, demo_actions, new_mission, normalize_mission_world,
    original_mission, resume_mission, simulate_mission,
)

SCHEMA = "skeleton.scene_mission_timeline.v1"
BUNDLE = "skeleton.scene_mission_timeline_bundle.v1"
MAX_BYTES = 2 * 1024 * 1024
MAX_BRANCHES = 12
MAX_ACTIONS = 128


def _bounded(value: Any) -> None:
    try:
        data = json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise SceneTravelError("invalid timeline JSON") from exc
    if len(data) > MAX_BYTES:
        raise SceneTravelError("timeline byte budget exceeded")


def _json(raw: str, label: str) -> Any:
    if type(raw) is not str or len(raw.encode("utf-8")) > MAX_BYTES:
        raise SceneTravelError(f"invalid or oversized {label} JSON")
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result
    def nonfinite(_: str) -> None:
        raise ValueError("nonfinite number")
    try:
        return json.loads(raw, object_pairs_hook=unique, parse_constant=nonfinite)
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise SceneTravelError(f"invalid {label} JSON") from exc


def _seal(record: dict[str, Any]) -> dict[str, Any]:
    clean = {key: value for key, value in record.items() if key != "digest"}
    clean["digest"] = dig(clean)
    _bounded(clean)
    return clean


def _replay(source: dict[str, Any], actions: list[dict[str, Any]]) -> dict[str, Any]:
    if type(actions) is not list or len(actions) > MAX_ACTIONS:
        raise SceneTravelError("timeline action budget exceeded")
    session = simulate_mission(source, actions)
    if [event["action"] for event in session["journal"]] != actions:
        raise SceneTravelError("noncanonical timeline action")
    return session


def _branch(name: str, parent: str | None, tick: int, checkpoint: str,
            actions: list[dict[str, Any]], session: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": name, "parent": parent, "fork_tick": tick,
        "fork_state_digest": checkpoint, "actions": actions,
        "head_state_digest": session["state_digest"],
        "head_save_digest": dig(session["save"]),
    }


def new_timeline(source: Any) -> dict[str, Any]:
    spec = normalize_mission_world(source)
    initial = new_mission(spec)
    return _seal({
        "schema_version": SCHEMA, "source": spec,
        "source_digest": dig(spec), "revision": 0,
        "active_branch": "main",
        "branches": [_branch("main", None, 0, initial["state_digest"], [], initial)],
    })


def verify_timeline(payload: Any) -> dict[str, Any]:
    _bounded(payload)
    obj = _object(payload, {
        "schema_version", "source", "source_digest", "revision",
        "active_branch", "branches", "digest",
    }, "timeline")
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported timeline schema")
    source = normalize_mission_world(obj["source"])
    if source != obj["source"] or obj["source_digest"] != dig(source):
        raise SceneTravelError("timeline source mismatch")
    revision = obj["revision"]
    if type(revision) is not int or not 0 <= revision <= 1000000:
        raise SceneTravelError("invalid timeline revision")
    if obj["digest"] != dig({k: v for k, v in obj.items() if k != "digest"}):
        raise SceneTravelError("timeline digest mismatch")
    branches = obj["branches"]
    if type(branches) is not list or not 1 <= len(branches) <= MAX_BRANCHES:
        raise SceneTravelError("invalid timeline branch count")
    seen: dict[str, dict[str, Any]] = {}
    initial = new_mission(source)
    for index, raw in enumerate(branches):
        item = _object(raw, {
            "id", "parent", "fork_tick", "fork_state_digest",
            "actions", "head_state_digest", "head_save_digest",
        }, "timeline branch")
        name = _id(item["id"], "branch id")
        if name in seen:
            raise SceneTravelError("duplicate timeline branch")
        tick, parent = item["fork_tick"], item["parent"]
        if type(tick) is not int or not 0 <= tick <= MAX_ACTIONS:
            raise SceneTravelError("invalid fork tick")
        if index == 0:
            if name != "main" or parent is not None or tick != 0:
                raise SceneTravelError("invalid timeline root")
            fork_session = initial
        else:
            if type(parent) is not str or parent not in seen:
                raise SceneTravelError("unknown or forward timeline parent")
            parent_actions = seen[parent]["actions"]
            if tick > len(parent_actions):
                raise SceneTravelError("fork exceeds parent history")
            fork_session = _replay(source, parent_actions[:tick])
        actions = item["actions"]
        if type(actions) is not list or len(actions) > MAX_ACTIONS:
            raise SceneTravelError("invalid timeline action count")
        if index and actions[:tick] != seen[parent]["actions"][:tick]:
            raise SceneTravelError("fork prefix mismatch")
        if item["fork_state_digest"] != fork_session["state_digest"]:
            raise SceneTravelError("fork checkpoint mismatch")
        session = _replay(source, actions)
        if (item["head_state_digest"] != session["state_digest"]
                or item["head_save_digest"] != dig(session["save"])):
            raise SceneTravelError("timeline head replay mismatch")
        seen[name] = item
    if obj["active_branch"] not in seen:
        raise SceneTravelError("unknown active branch")
    return obj


def _lease(record: dict[str, Any], revision: Any, digest: Any) -> None:
    if type(revision) is not int or revision != record["revision"]:
        raise SceneTravelError("stale timeline revision")
    if type(digest) is not str or digest != record["digest"]:
        raise SceneTravelError("stale timeline digest")
    if revision >= 1000000:
        raise SceneTravelError("timeline revision budget exceeded")


def _commit(record: dict[str, Any], branches: list[dict[str, Any]],
            active: str) -> dict[str, Any]:
    return _seal({
        **record, "branches": branches, "active_branch": active,
        "revision": record["revision"] + 1,
    })


def append_actions(payload: Any, branch_id: str, actions: Any, *,
                   expected_revision: int, expected_digest: str) -> dict[str, Any]:
    record = verify_timeline(payload)
    _lease(record, expected_revision, expected_digest)
    name = _id(branch_id, "branch id")
    if type(actions) is not list or not 1 <= len(actions) <= MAX_ACTIONS:
        raise SceneTravelError("invalid action batch")
    index = next((i for i, b in enumerate(record["branches"])
                  if b["id"] == name), None)
    if index is None:
        raise SceneTravelError("unknown timeline branch")
    old = record["branches"][index]
    if len(old["actions"]) + len(actions) > MAX_ACTIONS:
        raise SceneTravelError("timeline action budget exceeded")
    canonical = [_action(a) for a in actions]
    session = resume_mission(_replay(record["source"], old["actions"]), canonical)
    actions_out = [event["action"] for event in session["journal"]]
    branches = list(record["branches"])
    branches[index] = _branch(
        name, old["parent"], old["fork_tick"],
        old["fork_state_digest"], actions_out, session,
    )
    return _commit(record, branches, name)


def fork_branch(payload: Any, parent_id: str, new_id: str, tick: int, *,
                expected_revision: int, expected_digest: str) -> dict[str, Any]:
    record = verify_timeline(payload)
    _lease(record, expected_revision, expected_digest)
    name, parent_name = _id(new_id, "branch id"), _id(parent_id, "parent id")
    if len(record["branches"]) >= MAX_BRANCHES:
        raise SceneTravelError("timeline branch budget exceeded")
    if any(b["id"] == name for b in record["branches"]):
        raise SceneTravelError("duplicate timeline branch")
    parent = next((b for b in record["branches"]
                   if b["id"] == parent_name), None)
    if parent is None:
        raise SceneTravelError("unknown timeline parent")
    if type(tick) is not int or not 0 <= tick <= len(parent["actions"]):
        raise SceneTravelError("invalid fork tick")
    actions = list(parent["actions"][:tick])
    session = _replay(record["source"], actions)
    child = _branch(name, parent_name, tick, session["state_digest"],
                    actions, session)
    return _commit(record, [*record["branches"], child], name)


def checkout_branch(payload: Any, name: str, *,
                    expected_revision: int, expected_digest: str) -> dict[str, Any]:
    record = verify_timeline(payload)
    _lease(record, expected_revision, expected_digest)
    name = _id(name, "branch id")
    if not any(b["id"] == name for b in record["branches"]):
        raise SceneTravelError("unknown timeline branch")
    return _commit(record, list(record["branches"]), name)


def branch_session(payload: Any, name: str | None = None) -> dict[str, Any]:
    record = verify_timeline(payload)
    name = _id(name or record["active_branch"], "branch id")
    branch = next((b for b in record["branches"] if b["id"] == name), None)
    if branch is None:
        raise SceneTravelError("unknown timeline branch")
    return _replay(record["source"], branch["actions"])


def inspect_timeline(payload: Any) -> dict[str, Any]:
    record = verify_timeline(payload)
    out = []
    for branch in record["branches"]:
        session = _replay(record["source"], branch["actions"])
        state = session["state"]
        out.append({
            "id": branch["id"], "parent": branch["parent"],
            "fork_tick": branch["fork_tick"], "turns": len(branch["actions"]),
            "state_digest": session["state_digest"],
            "scene_id": state["scene"]["state"]["scene_id"],
            "missions": list(state["missions"]), "reputation": state["reputation"],
            "phase": state["phase"], "ending": state["ending"],
        })
    return {
        "schema_version": SCHEMA, "source_digest": record["source_digest"],
        "revision": record["revision"], "digest": record["digest"],
        "active_branch": record["active_branch"], "branches": out,
    }


def compare_branches(payload: Any, left: str, right: str) -> dict[str, Any]:
    record = verify_timeline(payload)
    names = {b["id"]: b for b in record["branches"]}
    left, right = _id(left, "left"), _id(right, "right")
    if left not in names or right not in names:
        raise SceneTravelError("unknown comparison branch")
    a, b = names[left]["actions"], names[right]["actions"]
    common = 0
    while common < min(len(a), len(b)) and a[common] == b[common]:
        common += 1
    sa, sb = _replay(record["source"], a), _replay(record["source"], b)
    la, rb = sa["state"], sb["state"]
    result = {
        "schema_version": SCHEMA, "timeline_digest": record["digest"],
        "source_digest": record["source_digest"], "left": left, "right": right,
        "common_turns": common, "left_turns": len(a), "right_turns": len(b),
        "same_head": sa["state_digest"] == sb["state_digest"],
        "new_missions_right": sorted(set(rb["missions"]) - set(la["missions"])),
        "lost_missions_right": sorted(set(la["missions"]) - set(rb["missions"])),
        "reputation_delta": rb["reputation"] - la["reputation"],
        "left_ending": la["ending"], "right_ending": rb["ending"],
    }
    result["receipt"] = dig(result)
    return result


def export_timeline(payload: Any) -> dict[str, Any]:
    record = verify_timeline(payload)
    bundle = {
        "schema_version": BUNDLE, "source_digest": record["source_digest"],
        "timeline_digest": record["digest"], "timeline": record,
    }
    bundle["checksum"] = dig(bundle)
    _bounded(bundle)
    return bundle


def import_timeline(payload: Any) -> dict[str, Any]:
    _bounded(payload)
    obj = _object(payload, {
        "schema_version", "source_digest", "timeline_digest", "timeline", "checksum",
    }, "timeline bundle")
    if obj["schema_version"] != BUNDLE:
        raise SceneTravelError("unsupported timeline bundle schema")
    if obj["checksum"] != dig({k: v for k, v in obj.items() if k != "checksum"}):
        raise SceneTravelError("timeline checksum mismatch")
    record = verify_timeline(obj["timeline"])
    if (obj["source_digest"] != record["source_digest"]
            or obj["timeline_digest"] != record["digest"]):
        raise SceneTravelError("timeline bundle source mismatch")
    return record


def demo_timeline() -> dict[str, Any]:
    record = new_timeline(original_mission())
    record = append_actions(
        record, "main", demo_actions(),
        expected_revision=record["revision"], expected_digest=record["digest"],
    )
    return fork_branch(
        record, "main", "alternate", 1,
        expected_revision=record["revision"], expected_digest=record["digest"],
    )


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-mission-timeline")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    for command in ("inspect", "verify", "export"):
        sub.add_parser(command).add_argument("--timeline-json", required=True)
    session = sub.add_parser("session")
    session.add_argument("--timeline-json", required=True)
    session.add_argument("--branch")
    compare = sub.add_parser("compare")
    compare.add_argument("--timeline-json", required=True)
    compare.add_argument("--left", required=True)
    compare.add_argument("--right", required=True)
    imported = sub.add_parser("import")
    imported.add_argument("--bundle-json", required=True)
    for command in ("append", "fork", "checkout"):
        cmd = sub.add_parser(command)
        cmd.add_argument("--timeline-json", required=True)
        cmd.add_argument("--branch", required=True)
        cmd.add_argument("--expected-revision", type=int, required=True)
        cmd.add_argument("--expected-digest", required=True)
        if command == "append":
            cmd.add_argument("--actions-json", required=True)
        if command == "fork":
            cmd.add_argument("--parent", required=True)
            cmd.add_argument("--tick", type=int, required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = demo_timeline()
        elif args.command == "import":
            result = import_timeline(_json(args.bundle_json, "bundle"))
        else:
            record = _json(args.timeline_json, "timeline")
            if args.command == "inspect":
                result = inspect_timeline(record)
            elif args.command == "verify":
                result = verify_timeline(record)
            elif args.command == "export":
                result = export_timeline(record)
            elif args.command == "session":
                result = branch_session(record, args.branch)
            elif args.command == "compare":
                result = compare_branches(record, args.left, args.right)
            else:
                lease = {
                    "expected_revision": args.expected_revision,
                    "expected_digest": args.expected_digest,
                }
                if args.command == "append":
                    result = append_actions(
                        record, args.branch, _json(args.actions_json, "actions"), **lease,
                    )
                elif args.command == "fork":
                    result = fork_branch(
                        record, args.parent, args.branch, args.tick, **lease,
                    )
                else:
                    result = checkout_branch(record, args.branch, **lease)
        _bounded(result)
        print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
        return 0
    except (SceneTravelError, TypeError, ValueError, KeyError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
