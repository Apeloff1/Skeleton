"""Source-bound scene advisories: authoring, masking, custody and CLI."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.jeeves.worlds.advisories import (
    AdvisoryStore, player_view, propose_advisories, validate_advisories,
)
from skeleton.jeeves.worlds.advisories_cli import run
from skeleton.jeeves.worlds.advisories_editor import render_advisories_editor
from skeleton.jeeves.worlds.session import SessionStore
from skeleton.jeeves.worlds.tools import SCHEMA, invoke_world_tool
from skeleton.jeeves.worlds.world_canon import (
    CanonError, WorldStore, canonical, digest, propose,
)


def setup(tmp_path):
    world = propose(world_id="beacon", premise="A storm closes in.",
                    protagonist="Ari", region="Harbor", goal="Restore the light")
    world["scenes"][0]["narrative"] = "</script><img src=x onerror=alert(1)>"
    WorldStore(tmp_path).publish(world, create=True)
    sessions = SessionStore(tmp_path)
    sessions.create("beacon", "player")
    entries = [
        {"scene": scene["id"],
         "categories": ["fear"] if scene["id"] == "opening" else [],
         "safe_summary": "A scene in the harbor."}
        for scene in sorted(world["scenes"], key=lambda s: s["id"])
    ]
    store = AdvisoryStore(tmp_path)
    source = store.propose("beacon", prompt="Provide optional scene warnings",
                           entries=entries)
    return world, sessions, store, source


def test_masking_requires_explicit_consent_and_approved_source(tmp_path):
    world, sessions, store, source = setup(tmp_path)
    with pytest.raises(CanonError, match="advisories_review_required"):
        player_view(source, world, sessions.read("beacon", "player"))
    lease = store.publish("beacon", source, create=True)
    approved = store.approve("beacon", lease, "Reviewed categories and safe summaries")
    hidden = store.player("beacon", "player")
    assert hidden["masked"] is True
    assert hidden["narrative"] == "A scene in the harbor."
    assert hidden["title"] == "Scene content notice"
    shown = store.player("beacon", "player", ["fear"])
    assert shown["masked"] is False
    assert shown["narrative"] == world["scenes"][0]["narrative"]
    assert shown["advisories_digest"] == approved


def test_exact_scene_coverage_category_bounds_and_no_review_bypass(tmp_path):
    world, _, store, source = setup(tmp_path)
    for bad in ([], source["entries"] + source["entries"][:1]):
        forged = copy.deepcopy(source)
        forged["entries"] = bad
        with pytest.raises(CanonError):
            validate_advisories(forged, world)
    forged = copy.deepcopy(source)
    forged["entries"][0]["categories"] = ["unknown"]
    with pytest.raises(CanonError, match="advisories_unknown_category"):
        validate_advisories(forged, world)
    forged = {**source, "approved": True, "review_note": "forged"}
    with pytest.raises(CanonError, match="advisories_approval_bypass"):
        store.publish("beacon", forged, create=True)
    store.publish("beacon", source, create=True)
    with pytest.raises(CanonError, match="advisories_stale_source"):
        store.publish("beacon", source, create=True)


def test_verified_compilation_and_stale_lease_rejection(tmp_path):
    _, sessions, store, source = setup(tmp_path)
    lease = store.publish("beacon", source, create=True)
    approved = store.approve("beacon", lease, "Reviewed")
    session = sessions.read("beacon", "player")
    with pytest.raises(CanonError, match="advisories_stale_lease"):
        store.compile("beacon", "player", "0" * 64, digest(session))
    receipt = store.compile("beacon", "player", approved, digest(session))
    assert receipt["masked"] is True
    assert store.verify("beacon", "player")["html_sha256"] == receipt["html_sha256"]
    page = (tmp_path / receipt["html_file"]).read_bytes()
    assert b"connect-src 'none'" in page
    assert b"<img src=x" not in page
    receipt = store.compile("beacon", "player", approved, digest(session), ["fear"])
    assert receipt["masked"] is False
    page = (tmp_path / receipt["html_file"]).read_bytes()
    assert b"<img src=x" not in page
    assert b"&lt;img" in page
    assert store.verify("beacon", "player") == {
        k: v for k, v in receipt.items() if k not in ("html_file", "receipt_file")
    }


def test_forged_receipt_and_world_revision_fail_closed(tmp_path):
    world, sessions, store, source = setup(tmp_path)
    lease = store.publish("beacon", source, create=True)
    approved = store.approve("beacon", lease, "Reviewed")
    session = sessions.read("beacon", "player")
    receipt = store.compile("beacon", "player", approved, digest(session))
    receipt_path = tmp_path / receipt["receipt_file"]
    forged = json.loads(receipt_path.read_text())
    forged["masked"] = False
    receipt_path.write_bytes(canonical(forged))
    with pytest.raises(CanonError, match="advisories_receipt_mismatch"):
        store.verify("beacon", "player")
    revised = copy.deepcopy(world)
    revised["prompt"] = "A changed world"
    with pytest.raises(CanonError, match="advisories_world_lease_mismatch"):
        validate_advisories(source, revised)


def test_cli_and_read_only_typed_jeeves_preview(tmp_path, capsys):
    _, _, store, source = setup(tmp_path)
    path = tmp_path / "proposal.json"
    path.write_bytes(canonical({"prompt": source["prompt"],
                                "entries": source["entries"]}))
    assert run(["--store", str(tmp_path), "propose", "--world-id", "beacon",
                "--file", str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["result"]["review_required"]
    result = invoke_world_tool(str(tmp_path), {
        "schema": SCHEMA, "tool": "world.advisories_propose_preview",
        "world_id": "beacon", "args": {
            "prompt": source["prompt"], "entries": source["entries"],
        },
    })
    assert result["persisted"] is False
    assert result["result"] == source


def test_editor_source_lease_and_script_injection(tmp_path):
    world, _, store, source = setup(tmp_path)
    source["entries"][0]["safe_summary"] = "</script><img src=x>"
    page = render_advisories_editor(source, world)
    assert b"<img src=x>" not in page
    assert b"\\u003c/script>" in page
    assert b"sha256-" in page
    assert b"Scene categories" in page
    assert b"checkbox" in page
    lease = store.publish("beacon", source, create=True)
    assert store.editor("beacon", lease)["source_digest"] == lease
    with pytest.raises(CanonError, match="advisories_stale_source"):
        store.editor("beacon", "0" * 64)
    store.approve("beacon", lease, "Reviewed")
    with pytest.raises(CanonError, match="advisories_editor_requires_draft"):
        store.editor("beacon", store.inspect("beacon")["source_digest"])
