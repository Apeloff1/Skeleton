"""Complete original translation coverage, review, replay, CLI and hostile inputs."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json

import pytest

from skeleton.jeeves.worlds.localization import (
    LocalizationStore, edit_localization, localized_replay,
    prove_localization, render_localization_html,
)
from skeleton.jeeves.worlds.localization_cli import run
from skeleton.jeeves.worlds.tools import invoke_world_tool, manifest
from skeleton.jeeves.worlds.world_canon import CanonError, WorldStore, digest, propose


def fixture(tmp_path):
    world = propose(world_id="harbor", premise="An original harbor mystery",
                    protagonist="Mara", region="Glass Bay", goal="Restore the archive")
    WorldStore(tmp_path).publish(world, create=True)
    locale = {
        "tag": "fr",
        "scenes": [{"id": row["id"], "title": "FR " + row["title"],
                    "narrative": "FR " + row["narrative"]}
                   for row in sorted(world["scenes"], key=lambda row: row["id"])],
        "choices": [{"id": row["id"], "label": "FR " + row["label"]}
                    for row in sorted(world["choices"], key=lambda row: row["id"])],
        "endings": [{"scene": row["scene"], "label": "FR " + row["label"]}
                    for row in sorted(world["endings"], key=lambda row: row["scene"])],
    }
    store = LocalizationStore(tmp_path)
    source = store.propose("harbor", prompt="Author a French original-world edition",
                           locale=locale)
    return world, store, source


def reject(code, fn):
    with pytest.raises(CanonError) as exc:
        fn()
    assert exc.value.code == code


def test_coverage_and_actual_player_replay(tmp_path):
    world, _, source = fixture(tmp_path)
    proof = prove_localization(source, world)
    assert proof["locales"][0]["scene_count"] == len(world["scenes"])
    replay = localized_replay(source, world, ["pursue_goal"], "fr")
    assert replay["ending"].startswith("FR ")
    assert replay["steps"][-1]["choice_label"].startswith("FR ")
    reject("localization_missing_locale",
           lambda: localized_replay(source, world, [], "de"))
    reject("session_invalid_transition",
           lambda: localized_replay(source, world, ["forged"], "fr"))


def test_review_compile_receipt_and_tamper(tmp_path):
    _, store, source = fixture(tmp_path)
    source["approved"] = True
    first = store.publish("harbor", source, create=True)
    assert store.inspect("harbor")["localization"]["approved"] is False
    reject("localization_review_required", lambda: store.compile("harbor", first))
    approved = store.approve("harbor", expected_digest=first, review_note="Reviewed")
    receipt = store.compile("harbor", approved)
    assert store.verify("harbor") == receipt
    page = tmp_path / receipt["html_file"]
    assert sha256(page.read_bytes()).hexdigest() == receipt["html_sha256"]
    assert b"connect-src 'none'" in page.read_bytes()
    page.write_bytes(page.read_bytes() + b"<!-- tampered -->")
    reject("localization_playable_mismatch", lambda: store.verify("harbor"))


def test_missing_coverage_invalid_locale_and_stale_lease(tmp_path):
    world, _, source = fixture(tmp_path)
    bad = deepcopy(source)
    bad["locales"][0]["scenes"].pop()
    reject("localization_scene_coverage", lambda: prove_localization(bad, world))
    bad = deepcopy(source)
    bad["locales"][0]["tag"] = "../fr"
    reject("localization_invalid_locale", lambda: prove_localization(bad, world))
    bad = deepcopy(source)
    bad["world_digest"] = "0" * 64
    reject("localization_source_lease_mismatch",
           lambda: prove_localization(bad, world))
    bad = deepcopy(source)
    bad["locales"][0]["choices"][0]["label"] = "\u0000"
    reject("control_character", lambda: prove_localization(bad, world))


def test_edit_lease_and_review_revocation(tmp_path):
    world, store, source = fixture(tmp_path)
    first = store.publish("harbor", source, create=True)
    edited = edit_localization(source, world, {
        "action": "replace_locale", "value": source["locales"][0]})
    assert not edited["approved"]
    reject("localization_stale_edit", lambda: store.publish(
        "harbor", edited, expected_digest="0" * 64))
    assert store.publish("harbor", edited, expected_digest=first)


def test_editor_cli_and_readonly_tools(tmp_path, capsys):
    _, store, source = fixture(tmp_path)
    first = store.publish("harbor", source, create=True)
    editor = store.editor("harbor", first)
    page = (tmp_path / editor["html_file"]).read_bytes()
    assert b"Export unapproved translations" in page
    assert b"connect-src 'none'" in page
    reject("localization_stale_edit", lambda: store.editor("harbor", "0" * 64))
    assert run(["--store", str(tmp_path), "inspect", "--world-id", "harbor"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    names = {item["name"] for item in manifest()["tools"]}
    assert {"world.localization_preview", "world.localization_propose_preview"} <= names
    response = invoke_world_tool(str(tmp_path), {
        "schema": "jeeves.world.tool_request.v1",
        "tool": "world.localization_preview", "world_id": "harbor", "args": {},
    })
    assert response["persisted"] is False
    assert response["result_digest"] == digest(response["result"])
    proposal = invoke_world_tool(str(tmp_path), {
        "schema": "jeeves.world.tool_request.v1",
        "tool": "world.localization_propose_preview", "world_id": "harbor",
        "args": {"prompt": "French edition", "locale": source["locales"][0]},
    })
    assert proposal["review_required"] is True
    assert proposal["result"]["approved"] is False


def test_placeholder_parity(tmp_path):
    world, _, source = fixture(tmp_path)
    world["scenes"][0]["title"] += " {hero}"
    source["world_digest"] = digest(world)
    reject("localization_placeholder_mismatch",
           lambda: prove_localization(source, world))
    source["locales"][0]["scenes"][0]["title"] += " {hero}"
    assert prove_localization(source, world)["locales"][0]["scene_count"] == 2
