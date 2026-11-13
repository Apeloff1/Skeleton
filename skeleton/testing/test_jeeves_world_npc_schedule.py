"""Original NPC itinerary proof, review, source leases and browser handoff."""
from __future__ import annotations

import copy
import json
import os

import pytest

from skeleton.jeeves.worlds.cast import CastStore, approve_cast, propose_cast
from skeleton.jeeves.worlds.npc_schedule import (
    ScheduleStore, approve_schedule, edit_schedule, propose_schedule,
    prove_schedule, render_schedule_html,
)
from skeleton.jeeves.worlds.npc_schedule_cli import run
from skeleton.jeeves.worlds.tools import invoke_world_tool
from skeleton.jeeves.worlds.world_canon import (
    CanonError, WorldStore, digest, propose,
)


def fixtures():
    world = propose(
        world_id="harbor", premise="An original harbor at sunrise.",
        protagonist="Ira", region="Harbor", goal="Reach the pier.",
    )
    cast = propose_cast(
        world, npc_id="guide", npc_name="Mira",
        npc_line="The pier is open to everyone.",
    )
    cast["characters"][0]["scenes"] = ["opening", "resolution"]
    return world, approve_cast(cast, world, "Reviewed original NPC.")


def proposal():
    world, cast = fixtures()
    return propose_schedule(
        world, cast, prompt="Place Mira at the harbor entrance.",
        actor="guide", scene="opening", first_tick=0, last_tick=0,
        label="Meet the harbor guide",
    )


def store_fixture(tmp_path):
    world, cast = fixtures()
    WorldStore(tmp_path).publish(world, create=True)
    CastStore(tmp_path).publish("harbor", cast, create=True)
    return ScheduleStore(tmp_path), world, cast


def test_prompt_proof_and_playable():
    world, cast = fixtures()
    draft = proposal()
    assert draft["approved"] is False
    report = prove_schedule(draft, world, cast)
    assert report["witnesses"]["first_appointment"] == {
        "scene": "opening", "tick": 0, "choices": [], "flags": [],
    }
    with pytest.raises(CanonError, match="npc_schedule_review_required"):
        render_schedule_html(draft, world, cast)
    approved = approve_schedule(draft, world, cast, "Reviewed original NPC.")
    playable = render_schedule_html(approved, world, cast).decode()
    assert "Content-Security-Policy" in playable
    assert "Scene tick:" in playable
    assert "Meet the harbor guide" in playable
    assert "script-src 'sha256-" in playable


@pytest.mark.parametrize("mutate,code", [
    (lambda d: d["appointments"][0].update(actor="unknown"),
     "npc_schedule_unknown_actor"),
    (lambda d: d["appointments"][0].update(scene="missing"),
     "npc_schedule_actor_absent"),
    (lambda d: d["appointments"][0].update(first_tick=5, last_tick=4),
     "npc_schedule_invalid_window"),
    (lambda d: d["appointments"][0].update(first_tick=2, last_tick=2),
     "npc_schedule_unreachable_appointment"),
    (lambda d: d["appointments"][0].update(requires_flags=["unearned"]),
     "npc_schedule_unreachable_appointment"),
    (lambda d: d["appointments"].append(copy.deepcopy(d["appointments"][0])),
     "npc_schedule_duplicate_appointment"),
    (lambda d: d.update(approved="yes"),
     "npc_schedule_invalid_approval"),
])
def test_invalid_itineraries_fail_closed(mutate, code):
    world, cast = fixtures()
    data = proposal()
    mutate(data)
    with pytest.raises(CanonError, match=code):
        prove_schedule(data, world, cast)


def test_double_booking_and_review_reset():
    world, cast = fixtures()
    data = proposal()
    new = {
        "id": "later_meeting", "actor": "guide", "scene": "resolution",
        "first_tick": 1, "last_tick": 1,
        "label": "Meet the guide at the pier", "requires_flags": [],
    }
    changed = edit_schedule(data, world, cast, {
        "action": "add", "value": new,
    })
    assert changed["approved"] is False
    assert prove_schedule(changed, world, cast)["witnesses"]["later_meeting"][
        "choices"
    ] == ["pursue_goal"]
    approved = approve_schedule(changed, world, cast, "Reviewed both meetings.")
    updated = edit_schedule(approved, world, cast, {
        "action": "replace", "value": {
            **new, "label": "A newly reviewed meeting is required",
        },
    })
    assert updated["approved"] is False
    overlap = copy.deepcopy(changed)
    overlap["appointments"][1]["first_tick"] = 0
    overlap["appointments"][1]["last_tick"] = 0
    with pytest.raises(CanonError, match="npc_schedule_double_booking"):
        prove_schedule(overlap, world, cast)


@pytest.mark.skipif(os.name != "posix", reason="descriptor anchored custody")
def test_full_source_leased_save_approve_compile_verify(tmp_path):
    store, world, cast = store_fixture(tmp_path)
    draft = proposal()
    lease = store.publish("harbor", draft, create=True)
    assert store.inspect("harbor")["proof"]["states_explored"] >= 2
    with pytest.raises(CanonError, match="npc_schedule_approval_requires_review"):
        store.publish(
            "harbor", approve_schedule(draft, world, cast, "Forged approval."),
            expected_digest=lease,
        )
    with pytest.raises(CanonError, match="npc_schedule_stale_edit"):
        store.publish("harbor", draft, expected_digest="0" * 64)
    approved = store.approve(
        "harbor", expected_digest=lease,
        review_note="Reviewed the original schedule.",
    )
    receipt = store.compile("harbor", approved)
    assert store.verify("harbor") == receipt
    html = tmp_path / "harbor.npc_schedule.playable.html"
    assert "Mira" in html.read_text()
    html.write_text("tampered")
    with pytest.raises(CanonError, match="npc_schedule_playable_mismatch"):
        store.verify("harbor")


@pytest.mark.skipif(os.name != "posix", reason="descriptor anchored custody")
def test_stale_cast_and_symlink_fail_closed(tmp_path):
    store, world, cast = store_fixture(tmp_path)
    draft = proposal()
    lease = store.publish("harbor", draft, create=True)
    approved = store.approve(
        "harbor", expected_digest=lease, review_note="Reviewed schedule.",
    )
    store.compile("harbor", approved)
    path = tmp_path / "harbor.npc_schedule.playable.html"
    path.unlink()
    path.symlink_to(tmp_path / "harbor.json")
    with pytest.raises((CanonError, OSError)):
        store.verify("harbor")
    path.unlink()
    store.compile("harbor", approved)
    changed = copy.deepcopy(cast)
    changed["lines"][0]["text"] = "Revised original line."
    CastStore(tmp_path).publish(
        "harbor", changed, expected_digest=digest(cast),
    )
    with pytest.raises(CanonError, match="npc_schedule_source_lease_mismatch"):
        store.verify("harbor")


@pytest.mark.skipif(os.name != "posix", reason="descriptor anchored custody")
def test_cli_and_read_only_jeeves_preview(tmp_path, capsys):
    store, world, cast = store_fixture(tmp_path)
    assert run([
        "--store", str(tmp_path), "propose", "--world-id", "harbor",
        "--prompt", "Original scene.", "--actor", "guide",
        "--scene", "opening", "--first-tick", "0", "--last-tick", "0",
        "--label", "Meet the guide",
    ]) == 0
    data = json.loads(capsys.readouterr().out)["proposal"]
    assert data["approved"] is False
    assert run([
        "--store", str(tmp_path), "save", "--world-id", "harbor",
        "--create", "--schedule-json", json.dumps(data),
    ]) == 0
    lease = json.loads(capsys.readouterr().out)["schedule_digest"]
    assert run([
        "--store", str(tmp_path), "approve", "--world-id", "harbor",
        "--expected-digest", lease, "--review-note", "Reviewed.",
    ]) == 0
    approved = json.loads(capsys.readouterr().out)["schedule_digest"]
    assert run([
        "--store", str(tmp_path), "compile", "--world-id", "harbor",
        "--expected-digest", approved,
    ]) == 0
    capsys.readouterr()
    assert run([
        "--store", str(tmp_path), "verify", "--world-id", "harbor",
    ]) == 0
    capsys.readouterr()
    result = invoke_world_tool(str(tmp_path), {
        "schema": "jeeves.world.tool_request.v1",
        "tool": "world.npc_schedule_preview", "world_id": "harbor",
        "args": {},
    })
    assert result["persisted"] is False
    assert result["result"]["proof"]["witnesses"]["first_appointment"][
        "tick"
    ] == 0

def test_unreviewed_cast_cannot_approve_schedule():
    world, cast = fixtures()
    draft = proposal()
    cast["approved"] = False
    draft["cast_digest"] = digest(cast)
    with pytest.raises(CanonError, match="npc_schedule_cast_review_required"):
        approve_schedule(draft, world, cast, "Attempted approval.")

@pytest.mark.skipif(os.name != "posix", reason="descriptor anchored custody")
def test_offline_editor_export_and_stale_lease(tmp_path):
    store, world, cast = store_fixture(tmp_path)
    draft = proposal()
    lease = store.publish("harbor", draft, create=True)
    result = store.editor("harbor", lease)
    assert result["schedule_digest"] == lease
    html = (tmp_path / result["html_file"]).read_text()
    assert "Content-Security-Policy" in html
    assert "Export unapproved JSON" in html
    assert "Add appointment" in html
    assert "source-digest" in html
    assert "script-src 'sha256-" in html
    with pytest.raises(CanonError, match="npc_schedule_stale_edit"):
        store.editor("harbor", "0" * 64)
