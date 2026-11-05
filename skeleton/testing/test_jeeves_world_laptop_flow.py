"""Original lighthouse laptop path: actual custody, review, builder, replay, restore."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from skeleton.jeeves.worlds.laptop_cli import run
from skeleton.jeeves.worlds.laptop_flow import LaptopFlow
from skeleton.jeeves.worlds.tools import invoke_world_tool, manifest
from skeleton.jeeves.worlds.world_canon import CanonError, canonical, digest

SAMPLES = Path(__file__).resolve().parents[2] / "examples" / "jeeves"


def sample(name):
    return json.loads((SAMPLES / name).read_text(encoding="utf-8"))


def reject(code, action):
    with pytest.raises(CanonError) as error:
        action()
    assert error.value.code == code


def ready(tmp_path):
    flow = LaptopFlow(tmp_path)
    proposed = flow.propose(sample("lighthouse_brief.json"))
    assert proposed["review_required"]
    assert not flow.inspect("lighthouse")["reviewed"]
    reviewed = flow.review(
        "lighthouse", proposed["source_digest"],
        sample("lighthouse_review.json"),
        "Author approved the original rescue branch and flag consequences.")
    receipt = flow.compile("lighthouse", reviewed["source_digest"])
    assert flow.verify("lighthouse") == receipt
    return flow, proposed, reviewed, receipt


def test_original_prompt_review_compile_and_builder_handoff(tmp_path):
    flow, proposed, reviewed, receipt = ready(tmp_path)
    assert reviewed["source_digest"] != proposed["source_digest"]
    assert receipt["source_digest"] == reviewed["source_digest"]
    manifest = json.loads((tmp_path / receipt["builder_file"]).read_text())
    assert manifest["schema"] == "jeeves.world.builder_handoff.v1"
    assert manifest["canon_proof"]["ending_witnesses"]["resolution"] == ["pursue_goal"]
    assert "rescue" in [c["id"] for c in manifest["choice_edges"]]
    assert manifest["session_contract"] == "jeeves.world.session.v1"
    assert manifest["qualification"].endswith("not_engine_binary_or_device_certified")
    assert "Content-Security-Policy" in (tmp_path / receipt["html_file"]).read_text()


def test_replay_export_restore_and_no_clobber(tmp_path):
    flow, _, _, _ = ready(tmp_path)
    first = flow.create_session("lighthouse", "one")
    assert first["scene"]["id"] == "opening"
    second = flow.choose("lighthouse", "one", "rescue", first["session_digest"])
    assert second["scene"]["id"] == "shelter"
    reject("stale_session", lambda: flow.choose(
        "lighthouse", "one", "return", first["session_digest"]))
    final = flow.choose("lighthouse", "one", "return", second["session_digest"])
    assert final["ending"] is not None
    exported = flow.export_session("lighthouse", "one")
    restored = flow.create_session("lighthouse", "two", imported=exported)
    assert restored["scene"] == final["scene"]
    assert restored["session_digest"] == final["session_digest"]
    reject("session_already_exists", lambda: flow.create_session(
        "lighthouse", "two", imported=exported))
    exported["session"]["scene"] = "opening"
    reject("session_checksum_mismatch", lambda: flow.create_session(
        "lighthouse", "three", imported=exported))


def test_stale_review_and_artifact_tampering_fail_closed(tmp_path):
    flow, proposed, reviewed, receipt = ready(tmp_path)
    reject("stale_source", lambda: flow.compile(
        "lighthouse", proposed["source_digest"]))
    (tmp_path / receipt["builder_file"]).write_bytes(
        (tmp_path / receipt["builder_file"]).read_bytes() + b" ")
    reject("laptop_builder_mismatch", lambda: flow.verify("lighthouse"))
    flow.compile("lighthouse", reviewed["source_digest"])
    (tmp_path / receipt["html_file"]).write_bytes(b"forged html")
    reject("laptop_html_mismatch", lambda: flow.verify("lighthouse"))
    flow.compile("lighthouse", reviewed["source_digest"])
    world = flow.worlds.read("lighthouse")
    changed = dict(world)
    changed["prompt"] = world["prompt"] + " revised"
    flow.worlds.publish(changed, expected_digest=digest(world))
    reject("review_stale_source", lambda: flow.verify("lighthouse"))
    reject("review_stale_source", lambda: flow.create_session("lighthouse", "one"))


def test_no_unreviewed_compile_and_bad_operations(tmp_path):
    flow = LaptopFlow(tmp_path)
    proposed = flow.propose(sample("lighthouse_brief.json"))
    reject("review_required", lambda: flow.compile(
        "lighthouse", proposed["source_digest"]))
    reject("review_note_too_short", lambda: flow.review(
        "lighthouse", proposed["source_digest"], sample("lighthouse_review.json"), "yes"))
    reject("review_requires_change", lambda: flow.review(
        "lighthouse", proposed["source_digest"],
        {"action": "batch", "value": [
            {"action": "replace_scene", "value": flow.worlds.read("lighthouse")["scenes"][0]}]},
        "Explicit but unchanged author review must fail."))
    reject("unsupported_edit", lambda: flow.review(
        "lighthouse", proposed["source_digest"],
        {"action": "shell", "value": {}},
        "Disallow arbitrary executable edit operations."))


def test_cli_end_to_end_and_typed_errors(tmp_path, capsys):
    root = str(tmp_path)
    assert run(["--store", root, "propose", "--brief-file",
                str(SAMPLES / "lighthouse_brief.json")]) == 0
    proposed = json.loads(capsys.readouterr().out)["result"]
    assert run(["--store", root, "review", "--world-id", "lighthouse",
                "--expected-digest", proposed["source_digest"],
                "--operation-file", str(SAMPLES / "lighthouse_review.json"),
                "--review-note", "Reviewed original lighthouse rescue branch."]) == 0
    reviewed = json.loads(capsys.readouterr().out)["result"]
    assert run(["--store", root, "compile", "--world-id", "lighthouse",
                "--expected-digest", reviewed["source_digest"]]) == 0
    assert json.loads(capsys.readouterr().out)["ok"]
    assert run(["--store", root, "verify", "--world-id", "lighthouse"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"]
    assert run(["--store", root, "session-create", "--world-id", "lighthouse",
                "--slot", "player"]) == 0
    view = json.loads(capsys.readouterr().out)["result"]
    assert run(["--store", root, "session-choose", "--world-id", "lighthouse",
                "--slot", "player", "--choice-id", "rescue",
                "--expected-session-digest", view["session_digest"]]) == 0
    assert json.loads(capsys.readouterr().out)["result"]["scene"]["id"] == "shelter"
    assert run(["--store", root, "session-export", "--world-id", "lighthouse",
                "--slot", "player"]) == 0
    exported = json.loads(capsys.readouterr().out)["result"]
    export_file = tmp_path / "export.json"
    export_file.write_bytes(canonical(exported))
    assert run(["--store", root, "session-restore", "--world-id", "lighthouse",
                "--slot", "restored", "--export-file", str(export_file)]) == 0
    assert json.loads(capsys.readouterr().out)["result"]["scene"]["id"] == "shelter"
    assert run(["--store", root, "compile", "--world-id", "lighthouse",
                "--expected-digest", "0" * 64]) == 2
    failure = json.loads(capsys.readouterr().out)
    assert failure["error"] == "stale_source"
    assert failure["phase"] == "compile"
    assert failure["next_action"] == "inspect_source_and_repeat_review"


def test_readonly_jeeves_preview_matches_compiled_source(tmp_path):
    flow, _, reviewed, receipt = ready(tmp_path)
    names = {item["name"] for item in manifest()["tools"]}
    assert {"world.laptop_preview", "world.laptop_handoff_preview"} <= names
    request = {"schema": "jeeves.world.tool_request.v1",
               "tool": "world.laptop_preview", "world_id": "lighthouse", "args": {}}
    response = invoke_world_tool(str(tmp_path), request)
    assert response["persisted"] is False
    assert response["result"]["source_digest"] == reviewed["source_digest"]
    assert response["result"]["reviewed"] is True
    request["tool"] = "world.laptop_handoff_preview"
    handoff = invoke_world_tool(str(tmp_path), request)
    assert handoff["persisted"] is False
    assert handoff["result"] == receipt
    assert handoff["result_digest"] == digest(receipt)


def test_existing_nine_plane_studio_engine_owner_bridge(tmp_path):
    from skeleton.testing.test_jeeves_world_studio_engine import fixture as engine_fixture
    engine_fixture(tmp_path)
    flow = LaptopFlow(tmp_path)
    source = flow.worlds.read("harbor")
    approved = flow.approve_current(
        "harbor", digest(source), "Existing canonical world explicitly reviewed.")
    assert approved["reviewed"] is True
    flow.compile("harbor", approved["source_digest"])
    preview = flow.engine_inspect("harbor", "eight_bit_tile_1983")
    assert preview["engine"]["source_digests"]["world"] == approved["source_digest"]
    stale = dict(preview["engine"]["source_digests"])
    stale["assets"] = "0" * 64
    reject("laptop_engine_stale_source", lambda: flow.engine_compile(
        "harbor", "eight_bit_tile_1983", stale))
    result = flow.engine_compile(
        "harbor", "eight_bit_tile_1983", preview["engine"]["source_digests"])
    assert flow.engine_verify("harbor") == result
    assert result["engine"]["qualification"] == (
        "source_verified_engine_recipe_not_release_certified")


def test_engine_bridge_never_synthesizes_missing_reviewed_planes(tmp_path):
    flow, _, _, _ = ready(tmp_path)
    reject("not_found", lambda: flow.engine_inspect(
        "lighthouse", "eight_bit_tile_1983"))


def test_readonly_prompt_to_typed_jeeves_proposal_never_persists(tmp_path):
    brief = sample("lighthouse_brief.json")
    response = invoke_world_tool(str(tmp_path), {
        "schema": "jeeves.world.tool_request.v1",
        "tool": "world.laptop_propose_preview",
        "world_id": brief["id"],
        "args": {k: brief[k] for k in ("premise", "protagonist", "region", "goal")},
    })
    assert response["persisted"] is False
    assert response["review_required"] is True
    assert response["result"]["world"]["id"] == "lighthouse"
    assert response["result"]["proof"]["ending_witnesses"]["resolution"] == ["pursue_goal"]
    assert not (tmp_path / "lighthouse.json").exists()
    assert response["world_digest"] == digest(response["result"]["world"])


def test_laptop_session_create_rejects_revision_between_verify_and_write(tmp_path, monkeypatch):
    flow, _, _, _ = ready(tmp_path)
    original = flow.sessions.create

    def concurrent_edit(world_id, slot, **kwargs):
        world = flow.worlds.read(world_id)
        changed = dict(world)
        changed["prompt"] = world["prompt"] + " unreviewed concurrent edit"
        flow.worlds.publish(changed, expected_digest=digest(world))
        return original(world_id, slot, **kwargs)

    monkeypatch.setattr(flow.sessions, "create", concurrent_edit)
    reject("session_world_lease_mismatch",
           lambda: flow.create_session("lighthouse", "raced"))
    assert not (tmp_path / "lighthouse.raced.session.json").exists()


def test_laptop_session_choose_rejects_revision_between_verify_and_write(tmp_path, monkeypatch):
    flow, _, _, _ = ready(tmp_path)
    initial = flow.create_session("lighthouse", "raced")
    path = tmp_path / "lighthouse.raced.session.json"
    before = path.read_bytes()
    original = flow.sessions.choose

    def concurrent_edit(world_id, slot, choice_id, expected_digest, **kwargs):
        world = flow.worlds.read(world_id)
        changed = dict(world)
        changed["prompt"] = world["prompt"] + " unreviewed concurrent edit"
        flow.worlds.publish(changed, expected_digest=digest(world))
        return original(world_id, slot, choice_id, expected_digest, **kwargs)

    monkeypatch.setattr(flow.sessions, "choose", concurrent_edit)
    reject("session_world_lease_mismatch", lambda: flow.choose(
        "lighthouse", "raced", "rescue", initial["session_digest"]))
    assert path.read_bytes() == before


def test_session_read_and_export_fail_if_source_changes_after_laptop_proof(tmp_path, monkeypatch):
    flow, _, _, _ = ready(tmp_path)
    flow.create_session("lighthouse", "raced")
    original = flow.sessions.inspect

    def concurrent_edit(world_id, slot, **kwargs):
        world = flow.worlds.read(world_id)
        changed = dict(world)
        changed["prompt"] = world["prompt"] + " unreviewed concurrent edit"
        flow.worlds.publish(changed, expected_digest=digest(world))
        return original(world_id, slot, **kwargs)

    monkeypatch.setattr(flow.sessions, "inspect", concurrent_edit)
    reject("session_world_lease_mismatch",
           lambda: flow.inspect_session("lighthouse", "raced"))


def test_laptop_restore_preflight_is_read_only_and_source_bound(tmp_path):
    flow, _, _, _ = ready(tmp_path)
    first = flow.create_session("lighthouse", "saved")
    flow.choose("lighthouse", "saved", "rescue", first["session_digest"])
    exported = flow.export_session("lighthouse", "saved")
    before = sorted(path.name for path in tmp_path.iterdir())
    checked = flow.preflight_restore("lighthouse", exported)
    assert checked["restorable"] is True
    assert checked["scene"] == "shelter"
    assert checked["revision"] == 1
    assert checked["qualification"] == "verified_preview_not_persisted"
    assert sorted(path.name for path in tmp_path.iterdir()) == before
    assert flow.create_session("lighthouse", "restored", imported=exported)["scene"]["id"] == "shelter"
    reject("session_already_exists", lambda: flow.create_session(
        "lighthouse", "restored", imported=exported))


def test_laptop_restore_preflight_rejects_forgery_and_unreviewed_source(tmp_path):
    flow, _, _, _ = ready(tmp_path)
    flow.create_session("lighthouse", "saved")
    exported = flow.export_session("lighthouse", "saved")
    forged = json.loads(json.dumps(exported))
    forged["session"]["scene"] = "resolution"
    reject("session_checksum_mismatch", lambda: flow.preflight_restore(
        "lighthouse", forged))
    world = flow.worlds.read("lighthouse")
    changed = dict(world)
    changed["prompt"] = world["prompt"] + " unreviewed"
    flow.worlds.publish(changed, expected_digest=digest(world))
    reject("review_stale_source", lambda: flow.preflight_restore(
        "lighthouse", exported))


def test_laptop_cli_restore_preflight_returns_actionable_error(tmp_path, capsys):
    flow, _, _, _ = ready(tmp_path)
    flow.create_session("lighthouse", "saved")
    export_file = tmp_path / "saved.json"
    export_file.write_bytes(canonical(flow.export_session("lighthouse", "saved")))
    assert run(["--store", str(tmp_path), "session-restore-check",
                "--world-id", "lighthouse", "--export-file", str(export_file)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["result"]["restorable"] is True
    assert not (tmp_path / "lighthouse.restored.session.json").exists()
    forged = json.loads(export_file.read_text())
    forged["session"]["scene"] = "resolution"
    export_file.write_bytes(canonical(forged))
    assert run(["--store", str(tmp_path), "session-restore-check",
                "--world-id", "lighthouse", "--export-file", str(export_file)]) == 2
    failure = json.loads(capsys.readouterr().out)
    assert failure["error"] == "session_checksum_mismatch"
    assert failure["next_action"] == "reject_export_and_restore_from_trusted_copy"


def test_laptop_diagnostic_reports_real_recovery_stages(tmp_path):
    flow = LaptopFlow(tmp_path)
    absent = flow.diagnose("lighthouse")
    assert absent["checks"]["source"]["error"] == "not_found"
    assert absent["next_action"] == "repair_or_restore_canonical_world_source"
    proposal = flow.propose(sample("lighthouse_brief.json"))
    pending = flow.diagnose("lighthouse")
    assert pending["checks"]["source"]["ok"] is True
    assert pending["checks"]["review"]["ok"] is False
    assert pending["next_action"] == "review_and_approve_canonical_source"
    reviewed = flow.review("lighthouse", proposal["source_digest"],
                           sample("lighthouse_review.json"),
                           "Reviewed original lighthouse rescue choices.")
    not_compiled = flow.diagnose("lighthouse")
    assert not_compiled["checks"]["builder"]["ok"] is False
    assert not_compiled["next_action"] == "compile_and_verify_reviewed_source"
    flow.compile("lighthouse", reviewed["source_digest"])
    ready_report = flow.diagnose("lighthouse")
    assert ready_report["checks"]["builder"]["ok"] is True
    assert ready_report["qualification"] == "diagnostic_only_not_consumer_or_device_certified"
    assert ready_report["next_action"] == "source_playable_handoff_ready_for_engine_validation"
    flow.create_session("lighthouse", "player")
    with_session = flow.diagnose("lighthouse", "player")
    assert with_session["checks"]["session"]["revision"] == 0
    (tmp_path / "lighthouse.player.session.json").write_bytes(b"{}")
    corrupted = flow.diagnose("lighthouse", "player")
    assert corrupted["checks"]["session"]["ok"] is False
    assert corrupted["next_action"] == "inspect_session_or_restore_from_trusted_export"


def test_laptop_diagnostic_cli_does_not_create_files(tmp_path, capsys):
    flow, _, _, _ = ready(tmp_path)
    before = sorted(path.name for path in tmp_path.iterdir())
    assert run(["--store", str(tmp_path), "diagnose",
                "--world-id", "lighthouse"]) == 0
    result = json.loads(capsys.readouterr().out)["result"]
    assert result["checks"]["builder"]["ok"] is True
    assert sorted(path.name for path in tmp_path.iterdir()) == before


def test_laptop_lease_filesystem_failure_is_typed_and_never_deletes_foreign_lock(tmp_path, monkeypatch):
    import errno
    import os

    flow = LaptopFlow(tmp_path)
    proposal = flow.propose(sample("lighthouse_brief.json"))
    lock = tmp_path / "lighthouse.lock"
    real_open = os.open

    def deny_lock(path, flags, *args, **kwargs):
        if path == "lighthouse.lock":
            raise PermissionError(errno.EACCES, "filesystem denied lock")
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", deny_lock)
    reject("lease_unavailable", lambda: flow.inspect("lighthouse"))
    assert not lock.exists()
    assert flow.worlds.read("lighthouse")["id"] == proposal["world_id"]


def test_laptop_lease_collision_preserves_existing_lock(tmp_path):
    flow = LaptopFlow(tmp_path)
    flow.propose(sample("lighthouse_brief.json"))
    lock = tmp_path / "lighthouse.lock"
    lock.write_bytes(b"other-writer")
    reject("lease_busy", lambda: flow.inspect("lighthouse"))
    assert lock.read_bytes() == b"other-writer"


def test_cli_unavailable_lease_preserves_foreign_lock_and_guides_recovery(tmp_path, capsys):
    """A failed lease open must not remove another writer's lock or claim success."""
    flow, _, _, _ = ready(tmp_path)
    lock = tmp_path / "lighthouse.lock"
    lock.write_text("foreign writer", encoding="utf-8")
    assert run(["--store", str(tmp_path), "verify", "--world-id", "lighthouse"]) == 2
    busy = json.loads(capsys.readouterr().out)
    assert busy["error"] == "lease_busy"
    assert busy["next_action"] == "retry_after_current_writer_finishes"
    assert lock.read_text(encoding="utf-8") == "foreign writer"


def test_cli_lease_permission_failure_has_specific_recovery(tmp_path, capsys, monkeypatch):
    """Permission failures are distinct from contention and never unlink locks."""
    flow, _, _, _ = ready(tmp_path)
    from skeleton.jeeves.worlds import laptop_flow
    real_open = laptop_flow.os.open

    def denied(path, flags, *args, **kwargs):
        if path == "lighthouse.lock" and flags & laptop_flow.os.O_EXCL:
            raise PermissionError("read-only custody")
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(laptop_flow.os, "open", denied)
    assert run(["--store", str(tmp_path), "verify", "--world-id", "lighthouse"]) == 2
    failure = json.loads(capsys.readouterr().out)
    assert failure["error"] == "lease_unavailable"
    assert failure["next_action"] == (
        "inspect_custody_permissions_and_retry_without_removing_foreign_locks")
    assert not (tmp_path / "lighthouse.lock").exists()


@pytest.mark.parametrize("failure_stage", [1, 2, 3, 4])
def test_laptop_diagnostic_distinguishes_unavailable_custody_at_each_stage(
        tmp_path, monkeypatch, failure_stage):
    """Read-only diagnostics never prescribe source repair for lease permissions."""
    flow, _, _, _ = ready(tmp_path)
    flow.create_session("lighthouse", "player")
    original = LaptopFlow._lock
    calls = 0

    def intermittent_lease(fd, world_id):
        nonlocal calls
        calls += 1
        if calls == failure_stage:
            raise CanonError("lease_unavailable")
        return original(fd, world_id)

    monkeypatch.setattr(LaptopFlow, "_lock", staticmethod(intermittent_lease))
    report = flow.diagnose("lighthouse", "player")
    assert report["next_action"] == (
        "inspect_custody_permissions_without_removing_foreign_locks")
    assert any(
        stage.get("error") == "lease_unavailable"
        for stage in report["checks"].values()
    )
    assert not (tmp_path / "lighthouse.lock").exists()
