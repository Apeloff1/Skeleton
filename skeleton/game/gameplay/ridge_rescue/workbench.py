"""Replay-verified map workbench for actual playable Cinder Ridge source.

Edits reuse the canonical world editor and reachability validator. The workbench
stores the full operation history, replays it before every change and never
modifies the caller's source or a running save in place.
"""
from __future__ import annotations
from copy import deepcopy
from typing import Any

from .authoring import revise, validate_reachability
from .custody import canonical, digest
from .schema import parse_world, world_dict
from .routebook import _document

SCHEMA = "ridge.rescue.workbench.v1"
EXPORT_SCHEMA = "ridge.rescue.workbench.export.v1"
MAX_OPERATIONS = 128
MAX_DOCUMENT = 512_000


class WorkbenchError(ValueError):
    pass


def _head(session: dict) -> str:
    return digest({key: value for key, value in session.items() if key != "head"})


def _operation(value: Any) -> dict:
    if not isinstance(value, dict) or set(value) != {"kind", "target", "value"}:
        raise WorkbenchError("invalid workbench operation")
    if not isinstance(value["kind"], str) or value["kind"] not in {
        "rename", "set-turn-budget", "move-civilian", "move-raider",
        "move-resource", "set-resource-count", "set-tile"
    }:
        raise WorkbenchError("unsupported workbench operation")
    return deepcopy(value)


def open_workbench(source: dict | str | bytes) -> dict:
    try:
        world = parse_world(source)
        validate_reachability(world)
    except (ValueError, TypeError, KeyError) as exc:
        raise WorkbenchError("invalid or unreachable workbench source") from exc
    normalized = world_dict(world)
    result = {"schema": SCHEMA, "origin": normalized, "origin_sha256": digest(normalized),
              "operations": [], "world": normalized, "revision_sha256": digest(normalized)}
    result["head"] = _head(result)
    return result


def verify_workbench(session: dict | str | bytes) -> dict:
    data = _document(session, MAX_DOCUMENT)
    if set(data) != {"schema", "origin", "origin_sha256", "operations",
                     "world", "revision_sha256", "head"} or data["schema"] != SCHEMA:
        raise WorkbenchError("invalid workbench session")
    try:
        world = parse_world(data["origin"])
        validate_reachability(world)
    except (ValueError, TypeError, KeyError) as exc:
        raise WorkbenchError("invalid workbench origin") from exc
    if canonical(world_dict(world)) != canonical(data["origin"]) or digest(data["origin"]) != data["origin_sha256"]:
        raise WorkbenchError("workbench origin mismatch")
    operations = data["operations"]
    if not isinstance(operations, list) or len(operations) > MAX_OPERATIONS:
        raise WorkbenchError("invalid workbench history length")
    for operation in operations:
        try:
            revision = revise(world, expected_sha256=digest(world_dict(world)), operation=_operation(operation))
            world = parse_world(revision["world"])
        except (ValueError, TypeError, KeyError) as exc:
            raise WorkbenchError("unreplayable workbench operation") from exc
    if canonical(world_dict(world)) != canonical(data["world"]) or digest(world_dict(world)) != data["revision_sha256"]:
        raise WorkbenchError("workbench final world mismatch")
    if not isinstance(data["head"], str) or data["head"] != _head(data):
        raise WorkbenchError("workbench head mismatch")
    return {"world": world, "head": data["head"], "operations": deepcopy(operations),
            "origin_sha256": data["origin_sha256"], "revision_sha256": data["revision_sha256"]}


def edit_workbench(session: dict, operation: dict, *, expected_head: str) -> dict:
    verified = verify_workbench(session)
    if not isinstance(expected_head, str) or expected_head != verified["head"]:
        raise WorkbenchError("stale workbench revision")
    if len(verified["operations"]) >= MAX_OPERATIONS:
        raise WorkbenchError("workbench operation budget exhausted")
    op = _operation(operation)
    try:
        revision = revise(verified["world"], expected_sha256=verified["revision_sha256"], operation=op)
    except (ValueError, TypeError, KeyError) as exc:
        raise WorkbenchError("workbench edit rejected") from exc
    result = deepcopy(session)
    result["operations"].append(op)
    result["world"] = revision["world"]
    result["revision_sha256"] = revision["sha256"]
    result["head"] = _head(result)
    if len(canonical(result)) > MAX_DOCUMENT:
        raise WorkbenchError("workbench byte budget exceeded")
    verify_workbench(result)
    return result


def undo_workbench(session: dict, *, expected_head: str) -> dict:
    verified = verify_workbench(session)
    if expected_head != verified["head"]:
        raise WorkbenchError("stale workbench revision")
    if not verified["operations"]:
        raise WorkbenchError("no workbench operation to undo")
    result = open_workbench(session["origin"])
    for operation in verified["operations"][:-1]:
        result = edit_workbench(result, operation, expected_head=result["head"])
    return result


def export_workbench(session: dict) -> dict:
    verified = verify_workbench(session)
    payload = {"schema": EXPORT_SCHEMA, "session": deepcopy(session),
               "world": world_dict(verified["world"]),
               "source_sha256": verified["revision_sha256"]}
    if len(canonical(payload)) > MAX_DOCUMENT:
        raise WorkbenchError("workbench export too large")
    return {"payload": payload, "sha256": digest(payload)}


def verify_workbench_export(bundle: dict | str | bytes) -> dict:
    data = _document(bundle, MAX_DOCUMENT)
    if set(data) != {"payload", "sha256"} or not isinstance(data["payload"], dict):
        raise WorkbenchError("invalid workbench export envelope")
    if digest(data["payload"]) != data["sha256"]:
        raise WorkbenchError("workbench export digest mismatch")
    payload = data["payload"]
    if set(payload) != {"schema", "session", "world", "source_sha256"} or payload["schema"] != EXPORT_SCHEMA:
        raise WorkbenchError("invalid workbench export payload")
    checked = verify_workbench(payload["session"])
    if canonical(payload["world"]) != canonical(world_dict(checked["world"])):
        raise WorkbenchError("workbench exported world mismatch")
    if payload["source_sha256"] != checked["revision_sha256"]:
        raise WorkbenchError("workbench export source digest mismatch")
    return checked


def preview_workbench(session: dict, actions: list[dict]) -> dict:
    checked = verify_workbench(session)
    from .custody import export_run, verify_run
    try:
        bundle = export_run(checked["world"], actions)
        replayed = verify_run(bundle)
    except (ValueError, TypeError, KeyError) as exc:
        raise WorkbenchError("workbench gameplay preview failed") from exc
    return {"schema": "ridge.rescue.workbench.preview.v1", "revision_sha256": checked["revision_sha256"],
            "status": replayed["state"]["status"], "turns": replayed["state"]["turn"],
            "bundle": bundle}
