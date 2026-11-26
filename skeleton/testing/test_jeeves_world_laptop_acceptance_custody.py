"""Deterministic Studio A recovery acceptance for reviewed lighthouse custody.

No native-model, engine binary, installer, or device readiness is inferred.
These fixtures exercise actual canonical source, reviewed compilation, save
isolation, and read-only diagnostic behavior against the integrated owners.
"""
from __future__ import annotations

import json

import pytest

from skeleton.jeeves.worlds.world_canon import CanonError, digest
from skeleton.testing.test_jeeves_world_laptop_flow import ready


def snapshot(root):
    return {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}


def test_acceptance_is_read_only_and_preserves_two_independent_saves(tmp_path):
    flow, _, _, receipt = ready(tmp_path)
    a = flow.create_session("lighthouse", "alice")
    b = flow.create_session("lighthouse", "bob")
    moved = flow.choose("lighthouse", "alice", "rescue", a["session_digest"])
    before = snapshot(tmp_path)
    accepted = flow.acceptance("lighthouse", "alice")
    assert accepted["source_digest"] == receipt["source_digest"]
    assert accepted["existing_session"]["session_digest"] == moved["session_digest"]
    assert accepted["existing_session"]["restorable"] is True
    assert accepted["portable_roundtrip_verified"] is True
    assert flow.inspect_session("lighthouse", "bob")["session_digest"] == b["session_digest"]
    assert snapshot(tmp_path) == before
    assert not (tmp_path / "lighthouse.lock").exists()


def test_diagnostic_reports_corrupted_handoff_without_mutating_saves(tmp_path):
    flow, _, reviewed, receipt = ready(tmp_path)
    session = flow.create_session("lighthouse", "alice")
    target = tmp_path / receipt["html_file"]
    target.write_bytes(b"corrupted offline player")
    before = snapshot(tmp_path)
    diagnosis = flow.diagnose("lighthouse", "alice")
    assert diagnosis["checks"]["source"]["ok"] is True
    assert diagnosis["checks"]["review"]["ok"] is True
    assert diagnosis["checks"]["builder"]["ok"] is False
    assert diagnosis["checks"]["builder"]["error"] == "laptop_html_mismatch"
    assert diagnosis["next_action"] == "compile_and_verify_reviewed_source"
    assert snapshot(tmp_path) == before
    assert flow.inspect("lighthouse")["source_digest"] == reviewed["source_digest"]
    with pytest.raises(CanonError) as error:
        flow.inspect_session("lighthouse", "alice")
    assert error.value.code == "laptop_html_mismatch"
    assert (tmp_path / "lighthouse.alice.session.json").is_file()


def test_source_revision_invalidates_recovery_but_never_overwrites_save(tmp_path):
    flow, _, _, receipt = ready(tmp_path)
    initial = flow.create_session("lighthouse", "alice")
    exported = flow.export_session("lighthouse", "alice")
    save = tmp_path / "lighthouse.alice.session.json"
    preserved = save.read_bytes()
    world = flow.worlds.read("lighthouse")
    changed = dict(world)
    changed["prompt"] = world["prompt"] + " new authored continuity"
    flow.worlds.publish(changed, expected_digest=digest(world))
    with pytest.raises(CanonError) as error:
        flow.preflight_restore("lighthouse", exported)
    assert error.value.code == "review_stale_source"
    assert save.read_bytes() == preserved
    diagnosis = flow.diagnose("lighthouse", "alice")
    assert diagnosis["checks"]["review"]["ok"] is False
    assert diagnosis["next_action"] == "review_and_approve_canonical_source"
    assert save.read_bytes() == preserved
    assert not (tmp_path / "lighthouse.lock").exists()


def test_busy_foreign_lease_is_not_deleted_by_diagnostic(tmp_path):
    flow, _, _, _ = ready(tmp_path)
    foreign = tmp_path / "lighthouse.lock"
    foreign.write_text("foreign writer", encoding="utf-8")
    before = snapshot(tmp_path)
    diagnosis = flow.diagnose("lighthouse")
    assert diagnosis["checks"]["source"] == {"ok": False, "error": "lease_busy"}
    assert diagnosis["next_action"] == "retry_after_current_writer_finishes"
    assert snapshot(tmp_path) == before
    assert foreign.read_text(encoding="utf-8") == "foreign writer"
