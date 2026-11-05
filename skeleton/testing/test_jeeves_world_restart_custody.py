"""Restart and custody regression for the original lighthouse authoring path.

These checks exercise durable state through independent flow instances, rather
than trusting in-memory objects returned by the initial authoring operation.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from skeleton.jeeves.worlds.laptop_flow import LaptopFlow
from skeleton.jeeves.worlds.world_canon import CanonError

SAMPLES = Path(__file__).resolve().parents[2] / "examples" / "jeeves"


def _sample(name: str):
    return json.loads((SAMPLES / name).read_text(encoding="utf-8"))


def _compiled(root: Path):
    author = LaptopFlow(root)
    proposal = author.propose(_sample("lighthouse_brief.json"))
    reviewed = author.review(
        "lighthouse", proposal["source_digest"],
        _sample("lighthouse_review.json"),
        "Approve the original rescue branch and its ending consequences.",
    )
    return author.compile("lighthouse", reviewed["source_digest"])


def test_restart_preserves_reviewed_handoff_and_save(tmp_path):
    receipt = _compiled(tmp_path)
    first = LaptopFlow(tmp_path)
    started = first.create_session("lighthouse", "save")
    advanced = first.choose(
        "lighthouse", "save", "rescue", started["session_digest"]
    )
    portable = first.export_session("lighthouse", "save")

    reopened = LaptopFlow(tmp_path)
    assert reopened.verify("lighthouse") == receipt
    assert reopened.inspect("lighthouse")["reviewed"] is True
    assert reopened.inspect_session("lighthouse", "save")["session_digest"] == advanced["session_digest"]
    preflight = reopened.preflight_restore("lighthouse", portable)
    assert isinstance(preflight, dict)
    restored = reopened.create_session("lighthouse", "restored", imported=portable)
    assert restored["session_digest"] == advanced["session_digest"]

    again = LaptopFlow(tmp_path)
    with pytest.raises(CanonError) as exc:
        again.create_session("lighthouse", "restored", imported=portable)
    assert exc.value.code == "session_already_exists"


def test_restart_detects_builder_corruption_before_session_mutation(tmp_path):
    receipt = _compiled(tmp_path)
    first = LaptopFlow(tmp_path)
    initial = first.create_session("lighthouse", "save")
    builder = tmp_path / receipt["builder_file"]
    builder.write_bytes(builder.read_bytes() + b" ")

    reopened = LaptopFlow(tmp_path)
    with pytest.raises(CanonError) as exc:
        reopened.choose("lighthouse", "save", "rescue", initial["session_digest"])
    assert exc.value.code == "laptop_builder_mismatch"
    # The failed operation must not advance the persisted session.
    assert LaptopFlow(tmp_path).sessions.inspect("lighthouse", "save")["session_digest"] == initial["session_digest"]


def test_restart_diagnostic_reports_session_lease_permission_failure(tmp_path, monkeypatch):
    """Permission-denied session custody is not a corrupt save or restore request."""
    _compiled(tmp_path)
    flow = LaptopFlow(tmp_path)
    flow.create_session("lighthouse", "save")

    def denied(*args, **kwargs):
        raise CanonError("lease_unavailable")

    monkeypatch.setattr(flow.sessions, "inspect", denied)
    report = flow.diagnose("lighthouse", "save")
    assert report["checks"]["source"] == {"ok": True}
    assert report["checks"]["builder"] == {"ok": True}
    assert report["checks"]["session"] == {
        "ok": False, "error": "lease_unavailable"
    }
    assert report["next_action"] == (
        "inspect_custody_permissions_without_removing_foreign_locks"
    )
    assert "acceptance" not in report["checks"]
    assert LaptopFlow(tmp_path).inspect_session("lighthouse", "save")["revision"] == 0


def test_diagnostic_refuses_mixed_session_revisions(tmp_path, monkeypatch):
    """A concurrently advanced save cannot be reported as a green handoff."""
    _compiled(tmp_path)
    flow = LaptopFlow(tmp_path)
    initial = flow.create_session("lighthouse", "save")
    original_acceptance = flow.acceptance

    def advance_before_acceptance(world_id, slot=None):
        flow.choose("lighthouse", "save", "rescue", initial["session_digest"])
        return original_acceptance(world_id, slot)

    monkeypatch.setattr(flow, "acceptance", advance_before_acceptance)
    report = flow.diagnose("lighthouse", "save")
    assert report["checks"]["source"] == {"ok": True}
    assert report["checks"]["builder"] == {"ok": True}
    assert report["checks"]["session"]["session_digest"] == initial["session_digest"]
    assert report["checks"]["acceptance"] == {
        "ok": False, "error": "laptop_diagnostic_source_changed"
    }
    assert report["next_action"] == "restart_diagnostic_after_source_change"
    assert LaptopFlow(tmp_path).inspect_session("lighthouse", "save")["revision"] == 1


def test_diagnostic_never_repairs_corrupted_builder_or_mutates_save(tmp_path):
    """Read-only recovery must preserve the original bytes and player revision."""
    receipt = _compiled(tmp_path)
    flow = LaptopFlow(tmp_path)
    initial = flow.create_session("lighthouse", "save")
    builder = tmp_path / receipt["builder_file"]
    corrupt = builder.read_bytes() + b"\\n"
    builder.write_bytes(corrupt)

    report = LaptopFlow(tmp_path).diagnose("lighthouse", "save")
    assert report["checks"]["source"] == {"ok": True}
    assert report["checks"]["review"] == {"ok": True}
    assert report["checks"]["builder"] == {
        "ok": False, "error": "laptop_builder_mismatch"
    }
    assert "session" not in report["checks"]
    assert "acceptance" not in report["checks"]
    assert report["next_action"] == "compile_and_verify_reviewed_source"
    assert builder.read_bytes() == corrupt
    assert LaptopFlow(tmp_path).sessions.inspect("lighthouse", "save")[
        "session_digest"
    ] == initial["session_digest"]
