"""Integrated Studio A: actual authored sources to one replay-proven offline player."""
from __future__ import annotations

from hashlib import sha256
import json
import pytest

from skeleton.jeeves.worlds.accessibility import AccessibilityStore
from skeleton.jeeves.worlds.cast import CastStore, approve_cast, propose_cast
from skeleton.jeeves.worlds.localization import LocalizationStore
from skeleton.jeeves.worlds.pacing import PacingStore
from skeleton.jeeves.worlds.rumors import RumorStore
from skeleton.jeeves.worlds.session import SessionStore
from skeleton.jeeves.worlds.studio_assembly import StudioAssemblyStore
from skeleton.jeeves.worlds.studio_assembly_cli import run
from skeleton.jeeves.worlds.testimony import TestimonyStore
from skeleton.jeeves.worlds.tools import invoke_world_tool, manifest
from skeleton.jeeves.worlds.world_canon import CanonError, WorldStore, digest, propose, prove


def fixture(tmp_path, *, leave_unapproved=False):
    world = propose(world_id="harbor", premise="An original harbor crisis",
                    protagonist="Mara", region="Glass Bay", goal="Save the beacon")
    world["scenes"].append({"id": "storm", "title": "Storm",
                            "narrative": "The beacon is threatened."})
    world["choices"][0]["to"] = "storm"
    world["choices"].append({"id": "save_beacon", "from": "storm", "to": "resolution",
                             "label": "Save the beacon", "requires": [], "grants": []})
    prove(world)
    WorldStore(tmp_path).publish(world, create=True)
    cast = propose_cast(world, npc_id="tala", npc_name="Tala",
                        npc_line="The storm is approaching.")
    cast["characters"][0]["scenes"] = ["opening", "resolution", "storm"]
    cast = approve_cast(cast, world, "Reviewed original cast")
    CastStore(tmp_path).publish("harbor", cast, create=True)
    testimony = TestimonyStore(tmp_path)
    testimony_source = testimony.propose(
        "harbor", prompt="Tala sees the storm", statement_id="storm_seen",
        actor="tala", scene="storm", choice="pursue_goal", claim="storm",
        stance="supports", text="The storm will reach the beacon.",
        provenance="firsthand")
    first = testimony.publish("harbor", testimony_source, create=True)
    if not leave_unapproved:
        testimony.approve("harbor", expected_digest=first, review_note="Reviewed")
    rumors = RumorStore(tmp_path)
    rumor_source = rumors.propose(
        "harbor", prompt="Tala warns the harbor", rumor_id="storm_warning",
        claim="storm", stance="supports", origin="tala",
        seed_choice="pursue_goal", text="The storm is coming.")
    first = rumors.publish("harbor", rumor_source, create=True)
    rumors.approve("harbor", expected_digest=first, review_note="Reviewed")
    locale = {"tag": "fr",
              "scenes": [{"id": row["id"], "title": "FR " + row["title"],
                          "narrative": "FR " + row["narrative"]}
                         for row in sorted(world["scenes"], key=lambda row: row["id"])],
              "choices": [{"id": row["id"], "label": "FR " + row["label"]}
                          for row in sorted(world["choices"], key=lambda row: row["id"])],
              "endings": [{"scene": row["scene"], "label": "FR " + row["label"]}
                          for row in sorted(world["endings"], key=lambda row: row["scene"])]}
    localization = LocalizationStore(tmp_path)
    first = localization.publish("harbor", localization.propose(
        "harbor", prompt="Original French edition", locale=locale), create=True)
    localization.approve("harbor", expected_digest=first, review_note="Reviewed")
    accessibility = AccessibilityStore(tmp_path)
    first = accessibility.publish("harbor", accessibility.propose(
        "harbor", prompt="Accessible beacon narrative",
        scenes=[{"id": row["id"], "summary": "Describe " + row["title"],
                 "landmark": "region"}
                for row in sorted(world["scenes"], key=lambda row: row["id"])],
        choices=[{"id": row["id"], "action": "Choose " + row["label"]}
                 for row in sorted(world["choices"], key=lambda row: row["id"])],
        endings=[{"scene": row["scene"], "summary": "Outcome " + row["label"]}
                 for row in sorted(world["endings"], key=lambda row: row["scene"])]),
        create=True)
    accessibility.approve("harbor", expected_digest=first, review_note="Reviewed")
    pacing = PacingStore(tmp_path)
    first = pacing.publish("harbor", pacing.propose(
        "harbor", prompt="Real climax and resolution",
        beats=[{"scene": "opening", "phase": "setup", "intensity": 2,
                "note": "Introduce the beacon."},
               {"scene": "resolution", "phase": "resolution", "intensity": 3,
                "note": "Resolve the storm."},
               {"scene": "storm", "phase": "climax", "intensity": 9,
                "note": "Face the storm."}]), create=True)
    pacing.approve("harbor", expected_digest=first, review_note="Reviewed")
    return StudioAssemblyStore(tmp_path)


def reject(code, fn):
    with pytest.raises(CanonError) as exc:
        fn()
    assert exc.value.code == code


def test_exact_source_compile_and_replay(tmp_path):
    store = fixture(tmp_path)
    inspected = store.inspect("harbor")
    receipt = store.compile("harbor", inspected["source_digests"])
    assert store.verify("harbor") == receipt
    page = tmp_path / "harbor.studio.playable.html"
    assert sha256(page.read_bytes()).hexdigest() == receipt["artifacts"][page.name]
    assert b"connect-src 'none'" in page.read_bytes()
    assert b"aria-label" in page.read_bytes()
    assert b"FR " in page.read_bytes()
    player = store.preview("harbor", ["pursue_goal", "save_beacon"], "fr")
    assert player["scene"] == "resolution"
    assert player["views"]["testimony"]["revealed_ids"] == ["storm_seen"]
    assert player["views"]["rumors"]["steps"][-1]["heard"][0]["actor"] == "tala"
    assert player["views"]["localization"]["ending"].startswith("FR ")
    assert player["views"]["pacing"]["steps"][1]["beat"]["phase"] == "climax"
    page.write_bytes(page.read_bytes() + b"<!-- tampered -->")
    reject("studio_assembly_artifact_mismatch", lambda: store.verify("harbor"))


def test_unapproved_or_stale_source_fails_closed(tmp_path):
    store = fixture(tmp_path, leave_unapproved=True)
    reject("studio_assembly_review_required", lambda: store.inspect("harbor"))
    reject("studio_assembly_review_required", lambda: store.compile(
        "harbor", {"world": "0" * 64}))
    first = store.testimony.inspect("harbor")["testimony"]
    store.testimony.approve("harbor", expected_digest=digest(first), review_note="Reviewed")
    inspected = store.inspect("harbor")
    stale = dict(inspected["source_digests"])
    stale["testimony"] = "0" * 64
    reject("studio_assembly_stale_source", lambda: store.compile("harbor", stale))


def test_player_session_cli_and_readonly_tool(tmp_path, capsys):
    store = fixture(tmp_path)
    session = SessionStore(tmp_path)
    session.create("harbor", "slot")
    current = session.read("harbor", "slot")
    session.choose("harbor", "slot", "pursue_goal", digest(current))
    current = session.read("harbor", "slot")
    session.choose("harbor", "slot", "save_beacon", digest(current))
    player = store.player("harbor", "slot", "fr")
    assert player["revision"] == 2
    assert player["player"]["ending"] == "Save the beacon"
    assert run(["--store", str(tmp_path), "inspect", "--world-id", "harbor"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    names = {item["name"] for item in manifest()["tools"]}
    assert {"world.studio_preview", "world.studio_player"} <= names
    response = invoke_world_tool(str(tmp_path), {
        "schema": "jeeves.world.tool_request.v1",
        "tool": "world.studio_preview", "world_id": "harbor", "args": {},
    })
    assert response["persisted"] is False
    assert response["result_digest"] == digest(response["result"])
    slot_view = invoke_world_tool(str(tmp_path), {
        "schema": "jeeves.world.tool_request.v1",
        "tool": "world.studio_player", "world_id": "harbor",
        "args": {"slot": "slot", "locale": "fr"},
    })
    assert slot_view["result"]["player"]["scene"] == "resolution"
