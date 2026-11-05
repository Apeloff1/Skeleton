"""Fail-closed laptop recovery checks for reviewed world custody.

These tests exercise the real canonical lighthouse handoff rather than mocks
of its review, builder, and session publication boundaries.
"""
from __future__ import annotations

import json

import pytest

from skeleton.jeeves.worlds.world_canon import CanonError, canonical
from skeleton.testing.test_jeeves_world_laptop_flow import ready


def assert_denied(code, action):
    with pytest.raises(CanonError) as exc:
        action()
    assert exc.value.code == code


@pytest.mark.parametrize("artifact,code", [
    ("html_file", "laptop_html_mismatch"),
    ("builder_file", "laptop_builder_mismatch"),
])
def test_corrupted_handoff_never_overwrites_existing_player_slot(
    tmp_path, artifact, code
):
    flow, _, _, receipt = ready(tmp_path)
    initial = flow.create_session("lighthouse", "player")
    slot = tmp_path / "lighthouse.player.session.json"
    before = slot.read_bytes()
    path = tmp_path / receipt[artifact]
    path.write_bytes(path.read_bytes() + b"\n")
    assert_denied(code, lambda: flow.choose(
        "lighthouse", "player", "rescue", initial["session_digest"]))
    assert slot.read_bytes() == before
    assert not (tmp_path / "lighthouse.lock").exists()


def test_replaced_review_rejects_portable_restore_without_creating_slot(tmp_path):
    flow, _, _, _ = ready(tmp_path)
    first = flow.create_session("lighthouse", "player")
    flow.choose("lighthouse", "player", "rescue", first["session_digest"])
    exported = flow.export_session("lighthouse", "player")
    original_slot = (tmp_path / "lighthouse.player.session.json").read_bytes()
    path = tmp_path / "lighthouse.laptop.review.json"
    review = json.loads(path.read_bytes())
    review["review_note"] = "Changed approval after portable export was issued."
    path.write_bytes(canonical(review))
    assert_denied("laptop_receipt_mismatch", lambda: flow.preflight_restore(
        "lighthouse", exported))
    assert_denied("laptop_receipt_mismatch", lambda: flow.create_session(
        "lighthouse", "restored", imported=exported))
    assert not (tmp_path / "lighthouse.restored.session.json").exists()
    assert (tmp_path / "lighthouse.player.session.json").read_bytes() == original_slot
    assert not (tmp_path / "lighthouse.lock").exists()


def test_recompile_restores_deterministic_builder_after_corruption(tmp_path):
    flow, _, reviewed, receipt = ready(tmp_path)
    builder = tmp_path / receipt["builder_file"]
    original = builder.read_bytes()
    builder.write_bytes(original + b"\n")
    assert_denied("laptop_builder_mismatch", lambda: flow.verify("lighthouse"))
    rebuilt = flow.compile("lighthouse", reviewed["source_digest"])
    assert rebuilt == receipt
    assert builder.read_bytes() == original
    assert flow.verify("lighthouse") == receipt
    assert not (tmp_path / "lighthouse.lock").exists()
