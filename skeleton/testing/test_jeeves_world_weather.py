"""Weather authoring, deterministic replay, custody, CLI and engine handoff."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.jeeves.worlds.weather import (
    WeatherStore, engine_handoff, propose_weather, validate_weather,
)
from skeleton.jeeves.worlds.weather_cli import run
from skeleton.jeeves.worlds.weather_editor import render_weather_editor
from skeleton.jeeves.worlds.session import SessionStore
from skeleton.jeeves.worlds.tools import SCHEMA, invoke_world_tool
from skeleton.jeeves.worlds.world_canon import (
    CanonError, WorldStore, canonical, digest, propose,
)


def setup(tmp_path):
    world = propose(world_id="harbor", premise="The lighthouse is dark.",
                    protagonist="Ari", region="Harbor", goal="Relight the beacon")
    WorldStore(tmp_path).publish(world, create=True)
    sessions = SessionStore(tmp_path)
    sessions.create("harbor", "slot")
    source = WeatherStore(tmp_path).propose(
        "harbor", prompt="A rainstorm clears when the beacon lights",
        scenes=[
            {"scene": "opening", "weather": "storm", "visibility": "obscured",
             "description": "The harbor is drenched."},
            {"scene": "resolution", "weather": "clear", "visibility": "clear",
             "description": "A <bright> sky."},
        ],
        overrides=[{"choice": "pursue_goal", "weather": "fog",
                    "visibility": "limited"}])
    return world, sessions, WeatherStore(tmp_path), source


def test_review_replay_and_choice_override(tmp_path):
    world, sessions, store, source = setup(tmp_path)
    with pytest.raises(CanonError, match="weather_review_required"):
        engine_handoff(source, world)
    lease = store.publish("harbor", source, create=True)
    approved = store.approve("harbor", lease, "Original weather reviewed")
    assert store.player("harbor", "slot")["weather"] == "storm"
    assert store.player("harbor", "slot")["weather_digest"] == approved
    assert engine_handoff(store.inspect("harbor")["source"], world)["choice_overrides"]
    session = sessions.read("harbor", "slot")
    receipt = store.compile("harbor", "slot", approved, digest(session))
    assert store.verify("harbor", "slot")["html_sha256"] == receipt["html_sha256"]
    page = (tmp_path / receipt["html_file"]).read_bytes()
    assert b"connect-src 'none'" in page
    assert b"<bright>" not in page
    with pytest.raises(CanonError, match="weather_stale_lease"):
        store.compile("harbor", "slot", approved, "0" * 64)
    sessions.choose("harbor", "slot", "pursue_goal", digest(session))
    progressed = store.player("harbor", "slot")
    assert progressed["scene"] == "resolution"
    assert progressed["weather"] == "fog"
    assert progressed["visibility"] == "limited"
    assert [step["choice"] for step in progressed["timeline"]] == [
        None, "pursue_goal",
    ]
    with pytest.raises(CanonError, match="weather_receipt_mismatch"):
        store.verify("harbor", "slot")
    next_session = sessions.read("harbor", "slot")
    store.compile("harbor", "slot", approved, digest(next_session))
    assert store.verify("harbor", "slot")["session_digest"] == digest(next_session)


def test_rejects_forged_conditions_overrides_and_approval(tmp_path):
    world, _, store, source = setup(tmp_path)
    for mutation in ("unknown_scene", "duplicate", "unknown_choice", "unknown_weather"):
        forged = copy.deepcopy(source)
        if mutation == "unknown_scene":
            forged["scenes"].pop()
        elif mutation == "duplicate":
            forged["overrides"].append(forged["overrides"][0])
        elif mutation == "unknown_choice":
            forged["overrides"][0]["choice"] = "unknown"
        else:
            forged["scenes"][0]["weather"] = "hurricane"
        with pytest.raises(CanonError):
            validate_weather(forged, world)
    forged = copy.deepcopy(source)
    forged["scenes"][0]["weather"] = []
    with pytest.raises(CanonError, match="weather_unknown_condition"):
        validate_weather(forged, world)
    forged = copy.deepcopy(source)
    forged["scenes"][0]["visibility"] = {}
    with pytest.raises(CanonError, match="weather_unknown_visibility"):
        validate_weather(forged, world)
    forged = {**source, "approved": True, "review_note": "fake"}
    with pytest.raises(CanonError, match="weather_approval_bypass"):
        store.publish("harbor", forged, create=True)
    lease = store.publish("harbor", source, create=True)
    with pytest.raises(CanonError, match="weather_stale_source"):
        store.approve("harbor", "0" * 64, "reviewed")
    store.approve("harbor", lease, "reviewed")


def test_receipt_tampering_fails_closed(tmp_path):
    _, sessions, store, source = setup(tmp_path)
    lease = store.publish("harbor", source, create=True)
    approved = store.approve("harbor", lease, "reviewed")
    receipt = store.compile("harbor", "slot", approved,
                            digest(sessions.read("harbor", "slot")))
    path = tmp_path / receipt["receipt_file"]
    forged = json.loads(path.read_text())
    forged["html_sha256"] = "0" * 64
    path.write_bytes(canonical(forged))
    with pytest.raises(CanonError, match="weather_receipt_mismatch"):
        store.verify("harbor", "slot")


def test_editor_and_read_only_typed_preview(tmp_path, capsys):
    world, _, store, source = setup(tmp_path)
    source["scenes"][0]["description"] = "</script><img src=x>"
    page = render_weather_editor(source, world)
    assert b"<img src=x>" not in page
    assert b"\\u003c/script>" in page
    assert b"sha256-" in page
    assert b"Choice weather overrides" in page
    assert b"Add choice override" in page
    assert b"Duplicate choice override" in page
    lease = store.publish("harbor", source, create=True)
    assert store.editor("harbor", lease)["source_digest"] == lease
    with pytest.raises(CanonError, match="weather_stale_source"):
        store.editor("harbor", "0" * 64)
    result = invoke_world_tool(str(tmp_path), {
        "schema": SCHEMA, "tool": "world.weather_propose_preview",
        "world_id": "harbor", "args": {
            "prompt": source["prompt"], "scenes": source["scenes"],
            "overrides": source["overrides"],
        },
    })
    assert result["persisted"] is False
    assert result["result"] == source
    proposal_path = tmp_path / "weather-proposal.json"
    proposal_path.write_bytes(canonical({
        "prompt": source["prompt"], "scenes": source["scenes"],
        "overrides": source["overrides"],
    }))
    assert run(["--store", str(tmp_path), "propose", "--world-id", "harbor",
                "--file", str(proposal_path)]) == 0
    assert json.loads(capsys.readouterr().out)["result"]["review_required"]


def test_interactive_weather_playable_compilation_and_tamper_proof(tmp_path):
    _, _, store, source = setup(tmp_path)
    lease = store.publish("harbor", source, create=True)
    with pytest.raises(CanonError, match="weather_review_required"):
        store.compile_playable("harbor", lease)
    approved = store.approve("harbor", lease, "Reviewed gameplay")
    with pytest.raises(CanonError, match="weather_stale_source"):
        store.compile_playable("harbor", "0" * 64)
    receipt = store.compile_playable("harbor", approved)
    assert store.verify_playable("harbor")["html_sha256"] == receipt["html_sha256"]
    page = (tmp_path / receipt["html_file"]).read_bytes()
    assert b"Choices taken:" in page
    assert b"weather-data" in page
    assert b"script-src 'sha256-" in page
    assert b"connect-src 'none'" in page
    assert b"new Set()" in page
    assert b"choice.requires.every" in page
    assert b"overrides.get(choice.id)" in page
    forged = json.loads((tmp_path / receipt["receipt_file"]).read_text())
    forged["weather_digest"] = "0" * 64
    (tmp_path / receipt["receipt_file"]).write_bytes(canonical(forged))
    with pytest.raises(CanonError, match="weather_playable_receipt_mismatch"):
        store.verify_playable("harbor")
