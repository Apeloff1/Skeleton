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


@pytest.mark.parametrize("mutation,expected", [
    ("scene", "session_checksum_mismatch"),
    ("revision", "session_checksum_mismatch"),
    ("trace", "session_checksum_mismatch"),
])
def test_portable_session_tampering_is_rejected_before_slot_publication(
    tmp_path, mutation, expected
):
    flow, _, _, _ = ready(tmp_path)
    first = flow.create_session("lighthouse", "original")
    flow.choose("lighthouse", "original", "rescue", first["session_digest"])
    exported = flow.export_session("lighthouse", "original")
    original_slot = (tmp_path / "lighthouse.original.session.json").read_bytes()
    tampered = json.loads(json.dumps(exported))
    session = tampered["session"]
    if mutation == "scene":
        session["scene"] = "resolution"
    elif mutation == "revision":
        session["revision"] = session["revision"] + 1
    else:
        session["trace"] = []
    assert_denied(expected, lambda: flow.preflight_restore(
        "lighthouse", tampered))
    assert_denied(expected, lambda: flow.create_session(
        "lighthouse", "untrusted", imported=tampered))
    assert not (tmp_path / "lighthouse.untrusted.session.json").exists()
    assert (tmp_path / "lighthouse.original.session.json").read_bytes() == original_slot
    assert not (tmp_path / "lighthouse.lock").exists()


def test_restore_preflight_is_non_mutating_for_valid_export(tmp_path):
    flow, _, _, _ = ready(tmp_path)
    initial = flow.create_session("lighthouse", "source")
    flow.choose("lighthouse", "source", "rescue", initial["session_digest"])
    exported = flow.export_session("lighthouse", "source")
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}
    preview = flow.preflight_restore("lighthouse", exported)
    assert preview["restorable"] is True
    after = {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}
    assert after == before
    assert not (tmp_path / "lighthouse.lock").exists()


def test_corrupted_compiled_artifacts_reject_restore_without_slot_creation(
    tmp_path
):
    flow, _, _, receipt = ready(tmp_path)
    flow.create_session("lighthouse", "source")
    exported = flow.export_session("lighthouse", "source")
    builder = tmp_path / receipt["builder_file"]
    original = builder.read_bytes()
    builder.write_bytes(original + b"\n")
    assert_denied("laptop_builder_mismatch", lambda: flow.preflight_restore(
        "lighthouse", exported))
    assert_denied("laptop_builder_mismatch", lambda: flow.create_session(
        "lighthouse", "restored", imported=exported))
    assert not (tmp_path / "lighthouse.restored.session.json").exists()
    assert not (tmp_path / "lighthouse.lock").exists()


def test_html_corruption_blocks_portable_restore_until_deterministic_recompile(tmp_path):
    flow, _, reviewed, receipt = ready(tmp_path)
    initial = flow.create_session("lighthouse", "source")
    flow.choose("lighthouse", "source", "rescue", initial["session_digest"])
    exported = flow.export_session("lighthouse", "source")
    source_slot = tmp_path / "lighthouse.source.session.json"
    source_bytes = source_slot.read_bytes()
    html = tmp_path / receipt["html_file"]
    original_html = html.read_bytes()
    html.write_bytes(original_html + b"\n<!-- modified after review -->\n")
    assert_denied("laptop_html_mismatch", lambda: flow.preflight_restore(
        "lighthouse", exported))
    assert_denied("laptop_html_mismatch", lambda: flow.create_session(
        "lighthouse", "recovered", imported=exported))
    assert not (tmp_path / "lighthouse.recovered.session.json").exists()
    assert source_slot.read_bytes() == source_bytes
    assert not (tmp_path / "lighthouse.lock").exists()
    rebuilt = flow.compile("lighthouse", reviewed["source_digest"])
    assert rebuilt == receipt
    assert html.read_bytes() == original_html
    assert flow.preflight_restore("lighthouse", exported)["restorable"] is True
    assert source_slot.read_bytes() == source_bytes
