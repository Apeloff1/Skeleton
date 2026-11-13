"""Patrol author CAS, source→preview→replay and corruption tests."""
import copy
import io
import json
from contextlib import redirect_stdout, redirect_stderr

import pytest

from skeleton.__main__ import main
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_guard_patrol import original_patrol, verify_patrol
from skeleton.game.gameplay.scene_guard_patrol_author import (
    edit_author, export_author, import_author, new_author,
    preview_author, verify_author,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def _edit(author, **fields):
    return {**fields, "expected_source_digest": author["source_digest"]}


def test_transactional_offset_edit_changes_real_guard_position():
    initial = new_author(original_patrol())
    revised = edit_author(initial, _edit(initial, kind="set_offset",
                                         guard_id="harbor_watch", value=1))
    assert initial["source"]["guards"][0]["offset"] == 0
    assert revised["source"]["guards"][0]["offset"] == 1
    assert verify_author(revised) == revised
    preview = preview_author(revised, [])
    assert preview["view"]["guards"][0]["scene_id"] == "gate"
    assert verify_patrol(preview["session"]) == preview["session"]


def test_bypass_edit_uses_only_authored_pickups():
    initial = new_author(original_patrol())
    revised = edit_author(initial, _edit(initial, kind="set_bypass",
                                         guard_id="harbor_watch", item_id="brass_key"))
    assert revised["source"]["guards"][0]["bypass_item"] == "brass_key"
    with pytest.raises(SceneTravelError, match="not authored"):
        edit_author(initial, _edit(initial, kind="set_bypass",
                                   guard_id="harbor_watch", item_id="master_key"))


def test_block_edit_is_validated_and_replayable():
    initial = new_author(original_patrol())
    revised = edit_author(initial, _edit(initial, kind="set_exit_block",
        guard_id="harbor_watch", scene_id="gate", exit_id="inside", blocked=False))
    assert len(revised["source"]["guards"][0]["blocked_exits"]) == 1
    assert verify_author(revised) == revised
    with pytest.raises(SceneTravelError, match="no effect"):
        edit_author(revised, _edit(revised, kind="set_exit_block",
            guard_id="harbor_watch", scene_id="gate", exit_id="inside", blocked=False))
    with pytest.raises(SceneTravelError):
        edit_author(initial, _edit(initial, kind="set_exit_block",
            guard_id="harbor_watch", scene_id="quay", exit_id="missing", blocked=True))


def test_stale_lease_and_forged_journal_fail_closed():
    initial = new_author(original_patrol())
    edit = _edit(initial, kind="rename_patrol", patrol_id="new_watch")
    revised = edit_author(initial, edit)
    with pytest.raises(SceneTravelError, match="stale"):
        edit_author(revised, edit)
    forged = copy.deepcopy(revised)
    forged["journal"][0]["after"] = "0" * 64
    forged["receipt"] = dig({"initial_source": forged["initial_source"],
                              "journal": forged["journal"]})
    with pytest.raises(SceneTravelError):
        verify_author(forged)
    assert initial["source"]["patrol_id"] == "lantern_watch"


def test_author_preview_rejects_illegal_gameplay_without_mutation():
    initial = new_author(original_patrol())
    before = copy.deepcopy(initial)
    with pytest.raises(SceneTravelError):
        preview_author(initial, [{"kind": "travel", "exit_id": "north"}])
    assert initial == before


def test_author_bundle_roundtrip_and_tamper_rejected():
    initial = new_author(original_patrol())
    bundle = export_author(initial)
    assert import_author(bundle) == initial
    bundle["checksum"] = "0" * 64
    with pytest.raises(SceneTravelError):
        import_author(bundle)


def test_cli_demo_and_bad_edit():
    out = io.StringIO()
    with redirect_stdout(out):
        assert main(["scene-patrol-author", "demo"]) == 0
    author = json.loads(out.getvalue())
    assert verify_author(author) == author
    error = io.StringIO()
    with redirect_stderr(error):
        assert main(["scene-patrol-author", "edit", "--author-json",
                     json.dumps(author), "--edit-json", '{"kind":"evil"}']) == 2
    assert '"ok": false' in error.getvalue()
