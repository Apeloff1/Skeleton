"""End-to-end item authoring, custody, proof, playable and adversarial contracts."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os

import pytest

from skeleton.jeeves.worlds.inventory import (
    InventoryStore, compile_inventory_html, edit_inventory, propose_inventory,
    prove_inventory, validate_inventory,
)
from skeleton.jeeves.worlds.inventory_cli import run
from skeleton.jeeves.worlds.tools import invoke_world_tool, manifest
from skeleton.jeeves.worlds.world_canon import (
    CanonError, WorldStore, canonical, digest, edit, propose,
)


def setup(tmp_path):
    worlds = WorldStore(tmp_path)
    world = propose(
        world_id="harbor", premise="An original lantern journey",
        protagonist="Mara", region="Saltglass", goal="Return the light",
    )
    worlds.publish(world, create=True)
    store = InventoryStore(str(tmp_path))
    source = store.propose(
        "harbor", prompt="The lantern is recovered by choice",
        item_id="lantern", name="Saltglass lantern",
        description="A hand-built glass beacon", pickup_choice="pursue_goal",
    )
    return worlds, store, world, source


def assert_code(code, fn):
    with pytest.raises(CanonError) as exc:
        fn()
    assert exc.value.code == code


def test_proposal_has_no_authority_and_source_lease(tmp_path):
    _, store, world, source = setup(tmp_path)
    assert source["approved"] is False
    assert prove_inventory(source, world)["effect_witnesses"] == {
        "pursue_goal": ["pursue_goal"]
    }
    assert_code("inventory_review_required",
                lambda: compile_inventory_html(source, world))
    wrong = deepcopy(source)
    wrong["world_digest"] = "0" * 64
    assert_code("inventory_source_lease_mismatch",
                lambda: validate_inventory(wrong, world))
    assert store.propose("harbor", prompt="A beacon", item_id="lantern",
                         name="Lantern", description="Glass",
                         pickup_choice="pursue_goal")["approved"] is False


def test_reviewed_save_compile_and_replay_receipt(tmp_path):
    _, store, world, source = setup(tmp_path)
    initial = store.publish("harbor", source, create=True)
    assert store.inspect("harbor")["proof"]["world_digest"] == digest(world)
    assert_code("inventory_review_required", lambda: store.compile("harbor", initial))
    approved = store.approve(
        "harbor", expected_digest=initial, review_note="Original author reviewed",
    )
    receipt = store.compile("harbor", approved)
    assert receipt == store.verify("harbor")
    assert receipt["inventory_digest"] == approved
    html_file = tmp_path / receipt["html_file"]
    payload = html_file.read_bytes()
    assert hashlib.sha256(payload).hexdigest() == receipt["html_sha256"]
    assert b"connect-src 'none'" in payload
    assert b"Saltglass lantern" in payload
    assert b"Inventory" in payload
    assert_code("inventory_stale_edit",
                lambda: store.compile("harbor", initial))
    assert_code("inventory_stale_edit",
                lambda: store.approve("harbor", expected_digest=initial,
                                     review_note="Stale"))


def test_edit_clears_review_and_invalidates_receipt(tmp_path):
    _, store, world, source = setup(tmp_path)
    original = store.publish("harbor", source, create=True)
    approved = store.approve("harbor", expected_digest=original,
                             review_note="Author reviewed")
    store.compile("harbor", approved)
    edited = edit_inventory(
        store.inspect("harbor")["inventory"], world,
        {"action": "replace_item", "value": {
            "id": "lantern", "name": "Polished lantern",
            "description": "A polished original beacon",
            "initial": 0, "capacity": 9,
        }},
    )
    assert edited["approved"] is False
    revision = store.publish("harbor", edited, expected_digest=approved)
    assert_code("inventory_review_required", lambda: store.verify("harbor"))
    assert_code("inventory_review_required", lambda: store.compile("harbor", revision))
    second = store.approve("harbor", expected_digest=revision,
                           review_note="Revision checked")
    assert_code("inventory_receipt_mismatch", lambda: store.verify("harbor"))
    store.compile("harbor", second)
    assert store.verify("harbor")["inventory_digest"] == second


def test_forged_approval_is_reset_by_save(tmp_path):
    _, store, _, source = setup(tmp_path)
    source["approved"] = True
    source["review_note"] = "Forged"
    published = store.publish("harbor", source, create=True)
    assert store.inspect("harbor")["inventory"]["approved"] is False
    assert published != digest(source)
    assert_code("inventory_review_required",
                lambda: store.compile("harbor", published))


def test_receipt_and_playable_tampering_fail_closed(tmp_path):
    _, store, _, source = setup(tmp_path)
    first = store.publish("harbor", source, create=True)
    second = store.approve("harbor", expected_digest=first,
                           review_note="Original author reviewed")
    receipt = store.compile("harbor", second)
    output = tmp_path / receipt["html_file"]
    output.write_bytes(output.read_bytes() + b"<!-- tampered -->")
    assert_code("inventory_playable_mismatch", lambda: store.verify("harbor"))
    store.compile("harbor", second)
    receipt_path = tmp_path / "harbor.inventory.receipt.json"
    receipt_path.write_bytes(b'{"schema":"fake"}')
    assert_code("inventory_receipt_mismatch", lambda: store.verify("harbor"))


def test_unknown_item_duplicate_choice_and_noncanonical_effects(tmp_path):
    _, _, world, source = setup(tmp_path)
    unknown = deepcopy(source)
    unknown["effects"][0]["gain"][0]["item"] = "missing"
    assert_code("inventory_unknown_item",
                lambda: validate_inventory(unknown, world))
    duplicate = deepcopy(source)
    duplicate["effects"].append(deepcopy(duplicate["effects"][0]))
    assert_code("inventory_invalid_choice",
                lambda: validate_inventory(duplicate, world))
    invalid = deepcopy(source)
    invalid["items"][0]["capacity"] = True
    assert_code("inventory_invalid_quantity",
                lambda: validate_inventory(invalid, world))
    invalid = deepcopy(source)
    invalid["effects"][0]["gain"][0]["quantity"] = 0
    assert_code("inventory_zero_effect",
                lambda: validate_inventory(invalid, world))


def test_spend_before_gain_and_inventory_deadlock(tmp_path):
    _, _, world, source = setup(tmp_path)
    source["effects"][0]["gain"] = []
    source["effects"][0]["spend"] = [{"item": "lantern", "quantity": 1}]
    assert_code("inventory_reachable_dead_end",
                lambda: prove_inventory(source, world))
    source["items"][0]["initial"] = 1
    report = prove_inventory(source, world)
    assert report["ending_witnesses"]["resolution"]["inventory"] == {"lantern": 0}
    source["items"][0]["capacity"] = 1
    source["effects"][0]["spend"] = []
    source["effects"][0]["gain"] = [{"item": "lantern", "quantity": 1}]
    assert_code("inventory_reachable_dead_end",
                lambda: prove_inventory(source, world))


def test_item_effects_are_world_choice_bound(tmp_path):
    _, _, world, source = setup(tmp_path)
    source["effects"][0]["choice"] = "nonexistent"
    assert_code("inventory_invalid_choice",
                lambda: prove_inventory(source, world))
    source["effects"][0]["choice"] = "pursue_goal"
    changed_world = edit(world, {"action": "replace_scene", "value": {
        "id": "opening", "title": "A new opening", "narrative": "New canon",
    }})
    assert_code("inventory_source_lease_mismatch",
                lambda: prove_inventory(source, changed_world))


def test_cli_full_authoring_flow(tmp_path, capsys):
    worlds, _, _, source = setup(tmp_path)
    root = str(tmp_path)
    def cli(*args):
        status = run(["--store", root, *args])
        response = json.loads(capsys.readouterr().out)
        return status, response
    status, proposed = cli(
        "propose", "--world-id", "harbor",
        "--prompt", "The recovered beacon", "--item-id", "lantern",
        "--name", "Lantern", "--description", "Glass",
        "--pickup-choice", "pursue_goal",
    )
    assert status == 0 and proposed["review_required"] is True
    status, saved = cli(
        "save", "--world-id", "harbor", "--create",
        "--inventory-json", json.dumps(source),
    )
    assert status == 0
    status, approved = cli(
        "approve", "--world-id", "harbor",
        "--expected-digest", saved["inventory_digest"],
        "--review-note", "Author reviewed",
    )
    assert status == 0
    status, compiled = cli(
        "compile", "--world-id", "harbor",
        "--expected-digest", approved["inventory_digest"],
    )
    assert status == 0 and compiled["receipt"]["world_id"] == "harbor"
    status, verified = cli("verify", "--world-id", "harbor")
    assert status == 0 and verified["receipt"] == compiled["receipt"]


def test_typed_jeeves_preview_has_no_write_authority(tmp_path):
    _, store, _, source = setup(tmp_path)
    request = {
        "schema": "jeeves.world.tool_request.v1",
        "tool": "world.inventory_propose_preview",
        "world_id": "harbor",
        "args": {
            "prompt": "Recover the lantern", "item_id": "lantern",
            "name": "Lantern", "description": "Glass",
            "pickup_choice": "pursue_goal",
        },
    }
    result = invoke_world_tool(str(tmp_path), request)
    assert result["persisted"] is False
    assert result["review_required"] is True
    assert result["result"]["approved"] is False
    assert not (tmp_path / "harbor.inventory.json").exists()
    assert any(x["name"] == request["tool"] and x["read_only"]
               for x in manifest()["tools"])
    store.publish("harbor", source, create=True)
    request["tool"] = "world.inventory_preview"
    request["args"] = {}
    assert invoke_world_tool(str(tmp_path), request)["result"]["inventory"]["approved"] is False


@pytest.mark.skipif(not hasattr(os, "O_NOFOLLOW"), reason="POSIX descriptor security required")
def test_symlink_source_is_not_followed(tmp_path):
    _, store, _, source = setup(tmp_path)
    target = tmp_path / "outside.json"
    target.write_bytes(canonical(source))
    (tmp_path / "harbor.inventory.json").symlink_to(target)
    with pytest.raises((CanonError, OSError)):
        store.inspect("harbor")
    assert target.read_bytes() == canonical(source)


def test_offline_editor_exports_unapproved_source(tmp_path, capsys):
    _, store, _, source = setup(tmp_path)
    first = store.publish("harbor", source, create=True)
    result = store.editor("harbor", first)
    content = (tmp_path / result["html_file"]).read_bytes()
    assert hashlib.sha256(content).hexdigest() == result["html_sha256"]
    assert b"connect-src 'none'" in content
    assert b"Export unapproved JSON" in content
    assert b"Review required after offline edit" in content
    assert b"fetch(" not in content
    assert_code("inventory_stale_edit",
                lambda: store.editor("harbor", "0" * 64))
    status = run(["--store", str(tmp_path), "editor", "--world-id", "harbor",
                  "--expected-digest", first])
    assert status == 0
    assert json.loads(capsys.readouterr().out)["editor"]["inventory_digest"] == first


def test_malformed_publish_is_typed_and_cannot_replace_source(tmp_path):
    _, store, _, source = setup(tmp_path)
    first = store.publish("harbor", source, create=True)
    assert_code("expected_object", lambda: store.publish(
        "harbor", [], expected_digest=first,
    ))
    assert store.inspect("harbor")["inventory"]["approved"] is False
    assert digest(store.inspect("harbor")["inventory"]) == first


def test_duplicate_items_and_conflicting_effects(tmp_path):
    _, _, world, source = setup(tmp_path)
    duplicate = deepcopy(source)
    duplicate["items"].append(deepcopy(duplicate["items"][0]))
    assert_code("inventory_duplicate_item",
                lambda: validate_inventory(duplicate, world))
    conflict = deepcopy(source)
    conflict["effects"][0]["spend"] = [{"item": "lantern", "quantity": 1}]
    assert_code("inventory_conflicting_effect",
                lambda: validate_inventory(conflict, world))
