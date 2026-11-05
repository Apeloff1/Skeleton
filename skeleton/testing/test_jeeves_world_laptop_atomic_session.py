"""The reviewed playable and player session share one custody lease."""
from __future__ import annotations
import json
import pytest
from skeleton.jeeves.worlds.session import SessionStore
from skeleton.jeeves.worlds.world_canon import CanonError, canonical
from skeleton.testing.test_jeeves_world_laptop_flow import ready


def rejects(code, action):
    with pytest.raises(CanonError) as error:
        action()
    assert error.value.code == code


def test_create_rejects_modified_html_without_slot(tmp_path):
    flow, _, _, receipt = ready(tmp_path)
    path = tmp_path / receipt["html_file"]
    path.write_bytes(path.read_bytes() + b" ")
    rejects("laptop_html_mismatch", lambda: flow.create_session("lighthouse", "player"))
    assert not (tmp_path / "lighthouse.player.session.json").exists()
    assert not (tmp_path / "lighthouse.lock").exists()


def test_choice_rejects_modified_builder_without_advancing(tmp_path):
    flow, _, _, receipt = ready(tmp_path)
    view = flow.create_session("lighthouse", "player")
    slot = tmp_path / "lighthouse.player.session.json"
    old = slot.read_bytes()
    builder = tmp_path / receipt["builder_file"]
    builder.write_bytes(builder.read_bytes() + b" ")
    rejects("laptop_builder_mismatch", lambda: flow.choose(
        "lighthouse", "player", "rescue", view["session_digest"]))
    assert slot.read_bytes() == old
    assert not (tmp_path / "lighthouse.lock").exists()


def test_inspect_export_restore_and_create_reject_replaced_review(tmp_path):
    flow, _, _, _ = ready(tmp_path)
    flow.create_session("lighthouse", "player")
    exported = flow.export_session("lighthouse", "player")
    path = tmp_path / "lighthouse.laptop.review.json"
    review = json.loads(path.read_bytes())
    review["review_note"] = "A distinct operator approval, same world source."
    path.write_bytes(canonical(review))
    for action in (
        lambda: flow.inspect_session("lighthouse", "player"),
        lambda: flow.export_session("lighthouse", "player"),
        lambda: flow.preflight_restore("lighthouse", exported),
        lambda: flow.create_session("lighthouse", "newslot", imported=exported),
    ):
        rejects("laptop_receipt_mismatch", action)
    assert not (tmp_path / "lighthouse.newslot.session.json").exists()
    assert not (tmp_path / "lighthouse.lock").exists()


def test_artifact_swap_before_session_lock_fails_closed(tmp_path, monkeypatch):
    flow, _, _, receipt = ready(tmp_path)
    original = SessionStore._lock
    builder = tmp_path / receipt["builder_file"]
    changed = []
    def swap(self, fd, world_id):
        if not changed:
            changed.append(True)
            builder.write_bytes(builder.read_bytes() + b" ")
        return original(self, fd, world_id)
    monkeypatch.setattr(SessionStore, "_lock", swap)
    rejects("laptop_builder_mismatch", lambda: flow.create_session("lighthouse", "player"))
    assert changed == [True]
    assert not (tmp_path / "lighthouse.player.session.json").exists()
    assert not (tmp_path / "lighthouse.lock").exists()


def test_normal_save_restore_and_acceptance_still_work(tmp_path):
    flow, _, _, _ = ready(tmp_path)
    view = flow.create_session("lighthouse", "player")
    next_view = flow.choose("lighthouse", "player", "rescue", view["session_digest"])
    exported = flow.export_session("lighthouse", "player")
    preview = flow.preflight_restore("lighthouse", exported)
    assert preview["session_digest"] == next_view["session_digest"]
    restored = flow.create_session("lighthouse", "restored", imported=exported)
    assert restored["session_digest"] == next_view["session_digest"]
    assert flow.inspect_session("lighthouse", "restored")["revision"] == 1
    assert flow.acceptance("lighthouse", "player")["persisted_slot_verified"]
    assert not (tmp_path / "lighthouse.lock").exists()
