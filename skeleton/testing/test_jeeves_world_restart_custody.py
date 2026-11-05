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


def test_cli_reopen_restores_exact_reviewed_world_without_rewriting_source(tmp_path, capsys):
    """A new CLI process can restore an exported save against the same canon."""
    from skeleton.jeeves.worlds.laptop_cli import run
    from skeleton.jeeves.worlds.world_canon import canonical

    root = str(tmp_path)
    assert run(["--store", root, "propose", "--brief-file",
                str(SAMPLES / "lighthouse_brief.json")]) == 0
    proposal = json.loads(capsys.readouterr().out)["result"]
    assert run(["--store", root, "review", "--world-id", "lighthouse",
                "--expected-digest", proposal["source_digest"],
                "--operation-file", str(SAMPLES / "lighthouse_review.json"),
                "--review-note", "Reviewed original lighthouse rescue and return."]) == 0
    reviewed = json.loads(capsys.readouterr().out)["result"]
    assert run(["--store", root, "compile", "--world-id", "lighthouse",
                "--expected-digest", reviewed["source_digest"]]) == 0
    receipt = json.loads(capsys.readouterr().out)["result"]
    assert run(["--store", root, "session-create", "--world-id", "lighthouse",
                "--slot", "original"]) == 0
    started = json.loads(capsys.readouterr().out)["result"]
    assert run(["--store", root, "session-choose", "--world-id", "lighthouse",
                "--slot", "original", "--choice-id", "rescue",
                "--expected-session-digest", started["session_digest"]]) == 0
    advanced = json.loads(capsys.readouterr().out)["result"]
    assert run(["--store", root, "session-export", "--world-id", "lighthouse",
                "--slot", "original"]) == 0
    portable = json.loads(capsys.readouterr().out)["result"]
    export_path = tmp_path / "portable.json"
    export_path.write_bytes(canonical(portable))
    source_path = tmp_path / "lighthouse.json"
    source_before = source_path.read_bytes()

    # Every invocation constructs a fresh flow; no cached in-memory authority.
    assert run(["--store", root, "session-restore-check", "--world-id", "lighthouse",
                "--export-file", str(export_path)]) == 0
    assert json.loads(capsys.readouterr().out)["ok"]
    assert run(["--store", root, "session-restore", "--world-id", "lighthouse",
                "--slot", "reopened", "--export-file", str(export_path)]) == 0
    restored = json.loads(capsys.readouterr().out)["result"]
    assert restored["session_digest"] == advanced["session_digest"]
    assert run(["--store", root, "verify", "--world-id", "lighthouse"]) == 0
    assert json.loads(capsys.readouterr().out)["result"] == receipt
    assert source_path.read_bytes() == source_before

    # A second import must not overwrite the previously restored save.
    save_path = tmp_path / "lighthouse.reopened.session.json"
    saved_bytes = save_path.read_bytes()
    assert run(["--store", root, "session-restore", "--world-id", "lighthouse",
                "--slot", "reopened", "--export-file", str(export_path)]) == 2
    failure = json.loads(capsys.readouterr().out)
    assert failure["error"] == "session_already_exists"
    assert failure["next_action"] == "select_an_unused_slot_without_overwriting"
    assert save_path.read_bytes() == saved_bytes


def test_cli_corrupt_export_fails_before_creating_restore_slot(tmp_path, capsys):
    """Corrupt portable replay cannot create a new session or rewrite canon."""
    from skeleton.jeeves.worlds.laptop_cli import run
    from skeleton.jeeves.worlds.world_canon import canonical

    _compiled(tmp_path)
    flow = LaptopFlow(tmp_path)
    flow.create_session("lighthouse", "original")
    portable = flow.export_session("lighthouse", "original")
    portable["session"]["scene"] = "forged_scene"
    export_path = tmp_path / "tampered.json"
    export_path.write_bytes(canonical(portable))
    source_path = tmp_path / "lighthouse.json"
    source_before = source_path.read_bytes()

    assert run(["--store", str(tmp_path), "session-restore-check",
                "--world-id", "lighthouse", "--export-file", str(export_path)]) == 2
    check = json.loads(capsys.readouterr().out)
    assert check["error"] == "session_checksum_mismatch"
    assert run(["--store", str(tmp_path), "session-restore",
                "--world-id", "lighthouse", "--slot", "forged",
                "--export-file", str(export_path)]) == 2
    failure = json.loads(capsys.readouterr().out)
    assert failure["error"] == "session_checksum_mismatch"
    assert failure["next_action"] == "reject_export_and_restore_from_trusted_copy"
    assert not (tmp_path / "lighthouse.forged.session.json").exists()
    assert source_path.read_bytes() == source_before


def test_session_writer_lease_permission_failure_is_typed_and_preserves_save(tmp_path, monkeypatch):
    """A denied session lock must not advance the saved player revision."""
    import errno
    import os
    from skeleton.jeeves.worlds import session as session_module

    _compiled(tmp_path)
    flow = LaptopFlow(tmp_path)
    initial = flow.create_session("lighthouse", "save")
    original_open = session_module.os.open

    def deny_session_lock(path, flags, *args, **kwargs):
        if path == "lighthouse.lock" and flags & os.O_EXCL:
            raise PermissionError(errno.EACCES, "permission denied", path)
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(session_module.os, "open", deny_session_lock)
    with pytest.raises(CanonError) as exc:
        flow.choose("lighthouse", "save", "rescue", initial["session_digest"])
    assert exc.value.code == "lease_unavailable"
    assert not (tmp_path / "lighthouse.lock").exists()
    # Unpatch before inspecting: only the denied operation is under test.
    monkeypatch.setattr(session_module.os, "open", original_open)
    assert LaptopFlow(tmp_path).inspect_session("lighthouse", "save")["session_digest"] == initial["session_digest"]


def test_session_lease_failure_does_not_delete_another_writers_lock(tmp_path, monkeypatch):
    """A failed acquisition must never remove a preexisting foreign lease."""
    import errno
    from skeleton.jeeves.worlds import session as session_module

    _compiled(tmp_path)
    lock = tmp_path / "lighthouse.lock"
    lock.write_bytes(b"foreign-writer-lease")
    original_open = session_module.os.open

    def deny_lock(path, flags, *args, **kwargs):
        if path == "lighthouse.lock":
            raise PermissionError(errno.EACCES, "permission denied", path)
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(session_module.os, "open", deny_lock)
    with pytest.raises(CanonError) as exc:
        LaptopFlow(tmp_path).create_session("lighthouse", "blocked")
    assert exc.value.code == "lease_unavailable"
    assert lock.read_bytes() == b"foreign-writer-lease"
    assert not (tmp_path / "lighthouse.blocked.session.json").exists()
