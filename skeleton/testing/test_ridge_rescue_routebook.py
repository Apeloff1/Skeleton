"""End-to-end source -> gameplay -> CAS journal -> portable routebook replay."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from skeleton.game.gameplay.ridge_rescue.custody import digest
from skeleton.game.gameplay.ridge_rescue.routebook import (
    RoutebookError, parse_routebook, open_route, step_route, run_route,
    verify_route, export_route, verify_route_export,
)
from skeleton.game.gameplay.ridge_rescue.routebook_editor import (
    revise_routebook, verify_routebook_revision,
)

SOURCE = Path(__file__).resolve().parents[1] / "game/gameplay/ridge_rescue/cinder_ridge_routebook.json"


def source():
    return json.loads(SOURCE.read_text(encoding="utf-8"))


@pytest.mark.parametrize("track,ending", [("protect-route", "protect"), ("salvage-route", "salvage")])
def test_source_to_earned_ending_and_portable_replay(track, ending):
    session = run_route(source(), track)
    verified = verify_route(session)
    assert verified["status"] == "completed"
    assert verified["state"]["status"] == "won:" + ending
    assert verified["state"]["civilians"]["tavi"] == "rescued"
    assert verified["cursor"] == len(verified["track"]["steps"])
    if ending == "protect":
        assert verified["state"]["flags"]["beacon"] is True
    export = export_route(session)
    assert verify_route_export(json.dumps(export))["head"] == session["head"]


def test_one_step_cas_and_replay():
    session = open_route(source(), "protect-route")
    first = step_route(session, expected_head=session["head"])
    assert session["cursor"] == 0
    assert first["cursor"] == 1
    assert first["journal"]["state"]["civilians"]["tavi"] == "rescued"
    with pytest.raises(RoutebookError, match="stale"):
        step_route(first, expected_head=session["head"])
    with pytest.raises(RoutebookError, match="completed"):
        completed = run_route(source(), "protect-route")
        step_route(completed, expected_head=completed["head"])


@pytest.mark.parametrize("mutation", [
    lambda x: x.update(head="0" * 64),
    lambda x: x.update(cursor=True),
    lambda x: x["journal"]["state"].update(health=10_000),
    lambda x: x["source"]["tracks"][0]["steps"][0]["action"].update(target="orin"),
    lambda x: x["journal"]["entries"][0].update(sha256="0" * 64),
    lambda x: x["source"].update(title="Different title"),
])
def test_rejects_tampered_sessions(mutation):
    session = run_route(source(), "protect-route")
    mutation(session)
    with pytest.raises(RoutebookError):
        verify_route(session)


def test_unsafe_action_never_published():
    session = open_route(source(), "protect-route")
    session["source"]["tracks"][0]["steps"][0]["action"] = {"verb": "evacuate", "choice": "protect"}
    session["source_sha256"] = digest(session["source"])
    from skeleton.game.gameplay.ridge_rescue.routebook import _head
    session["head"] = _head(session)
    with pytest.raises(RoutebookError):
        step_route(session, expected_head=session["head"])


def test_invalid_json_and_source_bounds():
    raw = SOURCE.read_text(encoding="utf-8")
    assert parse_routebook(raw)["schema"] == "ridge.rescue.routebook.v1"
    with pytest.raises(RoutebookError):
        parse_routebook('{"schema":"x","schema":"y"}')
    with pytest.raises(RoutebookError):
        parse_routebook(b"x" * 160_001)
    broken = source()
    broken["tracks"][0]["steps"][-1]["action"]["choice"] = "salvage"
    with pytest.raises(RoutebookError):
        parse_routebook(broken)


def test_edit_replays_and_rejects_non_playable_edits():
    original = source()
    op = {"expected_sha256": digest(parse_routebook(original)), "kind": "set-title",
          "track": "protect-route", "index": None, "value": "Protected Cinder Ridge"}
    revision = revise_routebook(original, op)
    assert verify_routebook_revision(original, revision, op)
    assert revision["source"]["tracks"][0]["title"] == "Protected Cinder Ridge"
    with pytest.raises(RoutebookError, match="stale"):
        revise_routebook(original, {**op, "expected_sha256": "0" * 64})
    bad = {**op, "kind": "set-action", "index": 0,
           "value": {"verb": "evacuate", "choice": "salvage"}}
    with pytest.raises(RoutebookError):
        revise_routebook(original, bad)


def test_export_tamper_rejected_even_if_outer_digest_recomputed():
    bundle = export_route(run_route(source(), "protect-route"))
    bundle["payload"]["gameplay"]["payload"]["state"]["health"] = 99
    bundle["sha256"] = digest(bundle["payload"])
    with pytest.raises(ValueError):
        verify_route_export(bundle)
