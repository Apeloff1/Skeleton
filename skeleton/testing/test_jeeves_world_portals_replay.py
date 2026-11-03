"""Browser portal-session source custody, replay and adversarial fixtures."""
from __future__ import annotations

import copy
import json
import os

import pytest

from skeleton.jeeves.worlds.portals import PortalStore
from skeleton.jeeves.worlds.portals_replay import replay_session
from skeleton.jeeves.worlds.portals_cli import run
from skeleton.jeeves.worlds.tools import invoke_world_tool
from skeleton.jeeves.worlds.world_canon import (
    CanonError, WorldStore, digest, propose,
)


def sources():
    return {
        wid: propose(
            world_id=wid, premise="An original " + wid + " journey.",
            protagonist="Ira", region=wid.title(), goal="Reach the end.",
        )
        for wid in ("harbor", "forest")
    }


def setup_store(tmp_path):
    for world in sources().values():
        WorldStore(tmp_path).publish(world, create=True)
    store = PortalStore(tmp_path)
    draft = store.propose(
        "journey", "A reviewed original crossing.",
        root_world="harbor", from_ending="resolution", to_world="forest",
    )
    lease = store.save("journey", draft, create=True)
    approved = store.approve(
        "journey", expected_network_digest=lease,
        review_note="Reviewed both original worlds and the crossing.",
    )
    store.compile("journey", expected_network_digest=approved)
    return store, store.inspect("journey")["network"]


def export(network):
    return {
        "schema": "jeeves.world.portal_session.v1",
        "network_id": network["id"], "network_digest": digest(network),
        "world_digests": network["world_digests"],
        "steps": [
            {"kind": "choice", "world": "harbor", "id": "pursue_goal"},
            {"kind": "portal", "world": "harbor", "id": "first_crossing"},
            {"kind": "choice", "world": "forest", "id": "pursue_goal"},
        ],
        "current_world": "forest", "current_scene": "resolution",
        "flags": {"forest": [], "harbor": []},
    }


def test_browser_trace_replays_to_verified_ending(tmp_path):
    store, network = setup_store(tmp_path)
    trace = export(network)
    report = replay_session(trace, network, sources())
    assert report["moves"] == 3
    assert report["ending_reached"] is True
    assert report["current_world"] == "forest"
    assert report["session_digest"] == digest(trace)
    assert report["witnesses"][1]["kind"] == "portal"
    assert store.preview_session("journey", trace) == report


@pytest.mark.parametrize("mutate,code", [
    (lambda s: s.update(network_digest="0" * 64),
     "portal_session_source_lease_mismatch"),
    (lambda s: s["steps"][0].update(id="missing"),
     "portal_session_invalid_choice"),
    (lambda s: s["steps"].pop(0),
     "portal_session_portal_before_ending"),
    (lambda s: s["steps"][1].update(world="forest"),
     "portal_session_wrong_world"),
    (lambda s: s["steps"][1].update(id="missing"),
     "portal_session_invalid_portal"),
    (lambda s: s["steps"][2].update(kind="invented"),
     "portal_session_invalid_step_kind"),
    (lambda s: s.update(current_scene="opening"),
     "portal_session_forged_position"),
    (lambda s: s["flags"].update(harbor=["invented"]),
     "portal_session_forged_flags"),
    (lambda s: s["steps"].extend([copy.deepcopy(s["steps"][0])] * 257),
     "invalid_list"),
])
def test_forged_browser_trace_fails_closed(tmp_path, mutate, code):
    store, network = setup_store(tmp_path)
    trace = export(network)
    mutate(trace)
    with pytest.raises(CanonError, match=code):
        store.preview_session("journey", trace)


@pytest.mark.skipif(os.name != "posix", reason="descriptor anchored custody")
def test_record_verify_and_optimistic_edit(tmp_path):
    store, network = setup_store(tmp_path)
    trace = export(network)
    first = store.record_session(
        "journey", "save1", trace, expected_network_digest=digest(network),
        create=True,
    )
    assert first == store.verify_session("journey", "save1")
    with pytest.raises(CanonError, match="portal_session_already_exists"):
        store.record_session(
            "journey", "save1", trace, expected_network_digest=digest(network),
            create=True,
        )
    with pytest.raises(CanonError, match="portal_session_stale_edit"):
        store.record_session(
            "journey", "save1", trace, expected_network_digest=digest(network),
            expected_session_digest="0" * 64,
        )
    next_trace = copy.deepcopy(trace)
    next_trace["steps"].pop()
    next_trace["current_scene"] = "opening"
    changed = store.record_session(
        "journey", "save1", next_trace,
        expected_network_digest=digest(network),
        expected_session_digest=first["session_digest"],
    )
    assert changed["report"]["moves"] == 2
    assert changed == store.verify_session("journey", "save1")


@pytest.mark.skipif(os.name != "posix", reason="descriptor anchored custody")
def test_tamper_and_stale_world_fail_closed(tmp_path):
    store, network = setup_store(tmp_path)
    trace = export(network)
    store.record_session(
        "journey", "save1", trace, expected_network_digest=digest(network),
        create=True,
    )
    path = tmp_path / "journey.portals.session.save1.json"
    raw = json.loads(path.read_text())
    raw["report"]["moves"] = 0
    path.write_text(json.dumps(raw))
    with pytest.raises(CanonError, match="portal_session_receipt_mismatch"):
        store.verify_session("journey", "save1")
    path.unlink()
    path.symlink_to(tmp_path / "harbor.json")
    with pytest.raises((CanonError, OSError)):
        store.verify_session("journey", "save1")


@pytest.mark.skipif(os.name != "posix", reason="descriptor anchored custody")
def test_compiled_playable_lease_and_cli(tmp_path, capsys):
    store, network = setup_store(tmp_path)
    trace = export(network)
    args = [
        "--store", str(tmp_path), "record-session", "--network-id", "journey",
        "--slot", "save1", "--create",
        "--expected-network-digest", digest(network),
        "--session-json", json.dumps(trace),
    ]
    assert run(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["ok"] is True
    assert run([
        "--store", str(tmp_path), "verify-session", "--network-id", "journey",
        "--slot", "save1",
    ]) == 0
    assert json.loads(capsys.readouterr().out)["result"] == result["result"]
    (tmp_path / "journey.portals.playable.html").write_text("tampered")
    with pytest.raises(CanonError, match="portals_playable_mismatch"):
        store.verify_session("journey", "save1")


@pytest.mark.skipif(os.name != "posix", reason="descriptor anchored custody")
def test_read_only_jeeves_preview_and_browser_export(tmp_path):
    store, network = setup_store(tmp_path)
    trace = export(network)
    result = invoke_world_tool(str(tmp_path), {
        "schema": "jeeves.world.tool_request.v1",
        "tool": "world.portals_session_preview",
        "world_id": "harbor",
        "args": {"network_id": "journey", "session": trace},
    })
    assert result["persisted"] is False
    assert result["result"]["moves"] == 3
    assert not (tmp_path / "journey.portals.session.save1.json").exists()
    html = (tmp_path / "journey.portals.playable.html").read_text()
    assert "Export session JSON" in html
    assert "portal_session.v1" in html
    assert "script-src 'sha256-" in html

def test_offline_browser_replay_has_source_bound_import():
    from skeleton.jeeves.worlds.portals import PLAYER_JS
    assert "Import session JSON" in PLAYER_JS
    assert "Restore locally checked session" in PLAYER_JS
    assert "data.network_digest !== model.proof.network_digest" in PLAYER_JS
    assert "Unreachable or unearned choice" in PLAYER_JS
    assert "Portal before ending" in PLAYER_JS
    assert "Session flags mismatch" in PLAYER_JS
    assert "data.steps.length > 256" in PLAYER_JS
