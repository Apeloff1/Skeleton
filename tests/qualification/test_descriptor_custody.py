"""Adversarial JSON custody: symlink, hardlink, FIFO, metadata race and size."""
from __future__ import annotations

import json
import os
from pathlib import Path
import pytest

from skeleton.qualification.errors import SchemaError
from skeleton.qualification.evidence import load_evidence
from skeleton.qualification.schema import load_case, load_cases

pytestmark = pytest.mark.skipif(os.name != "posix" or not hasattr(os, "O_NOFOLLOW"),
                               reason="POSIX descriptor-custody regression")

EVIDENCE = {"case_id": "GFM-X-01", "head_sha": "a" * 40, "source": "ci", "data": {"metric": 1}}
CASE = {"id": "GFM-PERF-77", "gate": "perf", "title": "bounded",
        "todo_ref": "P3", "severity": "sev2",
        "params": {"metric": "x", "budgets_ms": {"p95": 10}, "min_samples": 1}}


def _save(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")


def test_both_input_types_are_accepted_when_owned_and_stable(tmp_path):
    folder = tmp_path / "safe"
    folder.mkdir()
    _save(folder / "ev.json", EVIDENCE)
    assert load_evidence(folder)["GFM-X-01"].head_sha == "a" * 40
    (folder / "ev.json").unlink()
    _save(folder / "case.json", CASE)
    assert load_cases(folder)[0].id == "GFM-PERF-77"
    assert load_case(folder / "case.json").gate == "perf"


@pytest.mark.parametrize("read_case", [False, True])
def test_symlinked_parent_denied(tmp_path, read_case):
    owner = tmp_path / "owned"
    owner.mkdir()
    _save(owner / "item.json", CASE if read_case else EVIDENCE)
    alias = tmp_path / "alias"
    alias.symlink_to(owner, target_is_directory=True)
    with pytest.raises(SchemaError):
        if read_case:
            load_cases(alias)
        else:
            load_evidence(alias)


@pytest.mark.parametrize("read_case", [False, True])
def test_symlinked_member_denied(tmp_path, read_case):
    folder = tmp_path / "files"
    folder.mkdir()
    target = tmp_path / "original.json"
    _save(target, CASE if read_case else EVIDENCE)
    (folder / "alias.json").symlink_to(target)
    with pytest.raises(SchemaError):
        if read_case:
            load_case(folder / "alias.json")
        else:
            load_evidence(folder)


def test_hardlinked_member_is_never_admitted(tmp_path):
    folder = tmp_path / "files"
    folder.mkdir()
    target = folder / "real.json"
    _save(target, EVIDENCE)
    (folder / "linked.json").hardlink_to(target)
    with pytest.raises(SchemaError):
        load_evidence(folder)
    assert target.read_bytes() == json.dumps(EVIDENCE, sort_keys=True).encode("utf-8")


def test_special_fifo_fails_without_blocking(tmp_path):
    if not hasattr(os, "mkfifo"):
        pytest.skip("FIFO unavailable")
    os.mkfifo(tmp_path / "pipe.json", 0o600)
    with pytest.raises(SchemaError):
        load_evidence(tmp_path)


@pytest.mark.parametrize("reader", ["cases", "evidence"])
def test_group_writable_file_is_rejected(tmp_path, reader):
    data = CASE if reader == "cases" else EVIDENCE
    path = tmp_path / "x.json"
    _save(path, data)
    path.chmod(0o666)
    with pytest.raises(SchemaError):
        if reader == "cases":
            load_cases(tmp_path)
        else:
            load_evidence(tmp_path)


def test_oversized_bounded_evidence_denied(tmp_path):
    (tmp_path / "huge.json").write_bytes(b"x" * (262145))
    with pytest.raises(SchemaError):
        load_evidence(tmp_path)


def test_replacement_during_evidence_read_denied(tmp_path, monkeypatch):
    from skeleton.qualification import secure_fs
    path = tmp_path / "evidence.json"
    replacement = tmp_path / "replacement"
    _save(path, EVIDENCE)
    _save(replacement, EVIDENCE)
    previous = secure_fs.os.read
    once = False
    def swap(fd, count):
        nonlocal once
        block = previous(fd, count)
        if block and not once:
            once = True
            os.replace(replacement, path)
        return block
    monkeypatch.setattr(secure_fs.os, "read", swap)
    with pytest.raises(SchemaError):
        load_evidence(tmp_path)
    assert once


def test_directory_substitution_denied(tmp_path, monkeypatch):
    from skeleton.qualification import secure_fs
    folder = tmp_path / "original"
    folder.mkdir()
    _save(folder / "evidence.json", EVIDENCE)
    destination = tmp_path / "old"
    replacement = tmp_path / "replacement"
    replacement.mkdir()
    _save(replacement / "evidence.json", EVIDENCE)
    old_read = secure_fs._read
    once = False
    def swap_after_read(*args, **kwargs):
        nonlocal once
        data = old_read(*args, **kwargs)
        if not once:
            once = True
            os.rename(folder, destination)
            os.rename(replacement, folder)
        return data
    monkeypatch.setattr(secure_fs, "_read", swap_after_read)
    with pytest.raises(SchemaError):
        load_evidence(folder)
    assert once


def test_duplicate_and_nonfinite_case_json_denied(tmp_path):
    path = tmp_path / "case.json"
    path.write_bytes(b'{"id":"GFM-PERF-77","id":"GFM-PERF-77"}')
    with pytest.raises(SchemaError):
        load_case(path)
    path.write_bytes(json.dumps(CASE).replace('"p95": 10', '"p95": NaN').encode("utf-8"))
    with pytest.raises(SchemaError):
        load_case(path)


def test_untrusted_missing_directory_never_promotes_evidence(tmp_path):
    assert load_evidence(tmp_path / "unavailable") == {}
    assert load_cases(tmp_path / "unavailable") == []
