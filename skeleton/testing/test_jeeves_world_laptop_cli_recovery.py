"""CLI recovery actions must be typed, bounded and non-mutating on failure."""
from __future__ import annotations

import json
import os

import pytest

from skeleton.jeeves.worlds.laptop_cli import MAX_INPUT, run


@pytest.mark.parametrize(("content", "expected", "next_action"), [
    (b" " * (MAX_INPUT + 1), "input_too_large", "reduce_json_input_below_524288_bytes"),
    (b"{}", "input_invalid_path", "provide_a_normalized_existing_json_file_path"),
])
def test_laptop_cli_input_recovery_does_not_publish(tmp_path, capsys, content, expected, next_action):
    source = tmp_path / "brief.json"
    source.write_bytes(content)
    path = str(source) if expected == "input_too_large" else str(tmp_path / ".." / "brief.json")
    assert run(["--store", str(tmp_path), "propose", "--brief-file", path]) == 2
    failure = json.loads(capsys.readouterr().out)
    assert failure == {"ok": False, "phase": "propose", "error": expected,
                       "next_action": next_action}
    assert not any(p.name.endswith(".laptop.review.json") for p in tmp_path.iterdir())


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO unsupported")
def test_laptop_cli_pipe_rejection_is_nonblocking_and_actionable(tmp_path, capsys):
    pipe = tmp_path / "untrusted.json"
    os.mkfifo(pipe)
    assert run(["--store", str(tmp_path), "propose", "--brief-file", str(pipe)]) == 2
    failure = json.loads(capsys.readouterr().out)
    assert failure["error"] == "input_not_regular"
    assert failure["next_action"] == "provide_a_regular_json_file_not_a_device_or_pipe"


@pytest.mark.parametrize(("kind", "error", "next_action"), [
    ("missing", "input_missing", "verify_input_path_exists_before_retry"),
    ("non_directory", "input_invalid_directory", "replace_non_directory_parent_with_a_real_directory"),
    ("symlink", "input_symlink_disallowed", "use_a_regular_file_without_symlink_components"),
])
def test_laptop_cli_filesystem_errors_are_typed_and_do_not_publish(
    tmp_path, capsys, kind, error, next_action
):
    source = tmp_path / "brief.json"
    source.write_text('{"id":"original"}', encoding="utf-8")
    if kind == "missing":
        target = tmp_path / "missing.json"
    elif kind == "non_directory":
        target = source / "child.json"
    else:
        target = tmp_path / "alias.json"
        target.symlink_to(source)
    assert run(["--store", str(tmp_path), "propose", "--brief-file", str(target)]) == 2
    failure = json.loads(capsys.readouterr().out)
    assert failure == {"ok": False, "phase": "propose",
                       "error": error, "next_action": next_action}
    assert not any(p.name.endswith(".laptop.review.json") for p in tmp_path.iterdir())


def test_laptop_cli_rejects_input_mutated_during_descriptor_read(tmp_path, monkeypatch, capsys):
    """An input changed while read must never reach proposal publication."""
    source = tmp_path / "brief.json"
    source.write_text('{"id":"original"}', encoding="utf-8")
    original_fstat = os.fstat
    seen = 0

    def changed_fstat(fd):
        nonlocal seen
        result = original_fstat(fd)
        if (result.st_dev, result.st_ino) == (source.stat().st_dev, source.stat().st_ino):
            seen += 1
            if seen == 2:
                from types import SimpleNamespace
                return SimpleNamespace(
                    st_mode=result.st_mode, st_size=result.st_size + 1,
                    st_dev=result.st_dev, st_ino=result.st_ino,
                    st_mtime_ns=result.st_mtime_ns, st_ctime_ns=result.st_ctime_ns,
                )
        return result

    monkeypatch.setattr(os, "fstat", changed_fstat)
    assert run(["--store", str(tmp_path), "propose", "--brief-file", str(source)]) == 2
    failure = json.loads(capsys.readouterr().out)
    assert failure["error"] == "input_changed_during_read"
    assert failure["next_action"] == "retry_with_a_stable_unmodified_json_file"
    assert not any(p.name.endswith(".laptop.review.json") for p in tmp_path.iterdir())


@pytest.mark.parametrize("field", ["st_mtime_ns", "st_ctime_ns"])
def test_laptop_cli_rejects_same_size_metadata_change(tmp_path, monkeypatch, capsys, field):
    """Same-length rewrites are unsafe even when the input size is unchanged."""
    source = tmp_path / "brief.json"
    source.write_text('{"id":"original"}', encoding="utf-8")
    original_fstat = os.fstat
    seen = 0
    identity = source.stat()

    def modified_fstat(fd):
        nonlocal seen
        result = original_fstat(fd)
        if (result.st_dev, result.st_ino) == (identity.st_dev, identity.st_ino):
            seen += 1
            if seen == 2:
                from types import SimpleNamespace
                fields = {
                    "st_mode": result.st_mode,
                    "st_size": result.st_size,
                    "st_dev": result.st_dev,
                    "st_ino": result.st_ino,
                    "st_mtime_ns": result.st_mtime_ns,
                    "st_ctime_ns": result.st_ctime_ns,
                }
                fields[field] += 1
                return SimpleNamespace(**fields)
        return result

    monkeypatch.setattr(os, "fstat", modified_fstat)
    assert run(["--store", str(tmp_path), "propose", "--brief-file", str(source)]) == 2
    failure = json.loads(capsys.readouterr().out)
    assert failure["error"] == "input_changed_during_read"
    assert failure["next_action"] == "retry_with_a_stable_unmodified_json_file"
    assert not (tmp_path / "original.json").exists()
    assert not any(p.name.endswith(".laptop.review.json") for p in tmp_path.iterdir())


@pytest.mark.parametrize(("action", "argument"), [
    ("propose", "--brief-file"),
    ("session-restore-check", "--export-file"),
])
def test_invalid_external_json_never_initializes_canonical_store(
    tmp_path, capsys, action, argument
):
    """Reject untrusted input before even constructing canonical custody."""
    store = tmp_path / "not_created"
    source = tmp_path / "invalid.json"
    source.write_text('{"incomplete":', encoding="utf-8")
    args = ["--store", str(store), action]
    if action != "propose":
        args += ["--world-id", "original"]
    args += [argument, str(source)]
    assert run(args) == 2
    failure = json.loads(capsys.readouterr().out)
    assert failure["ok"] is False
    assert failure["phase"] == action
    assert not store.exists()


def test_invalid_review_input_does_not_initialize_custody(tmp_path, capsys):
    store = tmp_path / "not_created"
    source = tmp_path / "invalid.json"
    source.write_text('{"duplicate":1,"duplicate":2}', encoding="utf-8")
    assert run([
        "--store", str(store), "review", "--world-id", "original",
        "--expected-digest", "0" * 64, "--operation-file", str(source),
        "--review-note", "Operator reviewed original world",
    ]) == 2
    failure = json.loads(capsys.readouterr().out)
    assert failure["phase"] == "review"
    assert not store.exists()


@pytest.mark.parametrize(("action", "flag"), [
    ("propose", "--brief-file"),
    ("session-restore-check", "--export-file"),
    ("engine-compile", "--expected-digests-file"),
])
def test_empty_external_json_is_actionable_and_never_initializes_custody(
    tmp_path, capsys, action, flag
):
    source = tmp_path / "empty.json"
    source.write_bytes(b"")
    store = tmp_path / "uncreated-store"
    args = ["--store", str(store), action]
    if action != "propose":
        args += ["--world-id", "original"]
    if action == "engine-compile":
        args += ["--era", "classic"]
    args += [flag, str(source)]
    assert run(args) == 2
    assert json.loads(capsys.readouterr().out) == {
        "ok": False, "phase": action, "error": "input_empty",
        "next_action": "provide_a_nonempty_valid_json_document",
    }
    assert not store.exists()
