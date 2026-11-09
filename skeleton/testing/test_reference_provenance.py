from __future__ import annotations

import json
import os
from pathlib import Path
import threading

import pytest

import skeleton.cortex.reference_provenance as provenance
from skeleton.cortex.reference_provenance import (
    ReferenceProvenanceError,
    append_reference,
    read_reference_log,
    reference_scope,
    runtime_provenance_path,
)
from skeleton.cortex.refs import (
    GameRefPort,
    provenance_path,
    read_provenance,
    record_provenance,
)


def _ref(**overrides: object) -> dict[str, object]:
    ref: dict[str, object] = {
        "appid": 1245620,
        "title": "Reference Fixture",
        "url": "https://example.invalid/reference-fixture",
        "license": "pointer-only",
        "dialect": "house",
    }
    ref.update(overrides)
    return ref


def _journal(root: Path) -> Path:
    return root / ".skeleton" / "references" / "provenance.jsonl"


def test_runtime_path_resolution_does_not_create_state(tmp_path: Path) -> None:
    path = runtime_provenance_path(tmp_path)

    assert path == _journal(tmp_path)
    assert not path.exists()
    assert not path.parent.exists()


def test_default_runtime_path_uses_current_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert runtime_provenance_path() == _journal(tmp_path)
    assert provenance_path() == _journal(tmp_path)
    assert not _journal(tmp_path).exists()


def test_explicit_root_overrides_active_scope(tmp_path: Path) -> None:
    outer = tmp_path / "outer"
    explicit = tmp_path / "explicit"

    with reference_scope(outer):
        assert runtime_provenance_path() == _journal(outer)
        assert runtime_provenance_path(explicit) == _journal(explicit)


def test_nested_scopes_restore_previous_root(tmp_path: Path) -> None:
    outer = tmp_path / "outer"
    inner = tmp_path / "inner"

    with reference_scope(outer):
        assert runtime_provenance_path() == _journal(outer)
        with reference_scope(inner):
            assert runtime_provenance_path() == _journal(inner)
        assert runtime_provenance_path() == _journal(outer)


def test_scope_restores_after_exception(tmp_path: Path) -> None:
    before = runtime_provenance_path()
    scoped = tmp_path / "scoped"

    with pytest.raises(RuntimeError, match="boom"):
        with reference_scope(scoped):
            assert runtime_provenance_path() == _journal(scoped)
            raise RuntimeError("boom")

    assert runtime_provenance_path() == before


def test_context_local_scopes_do_not_cross_threads(tmp_path: Path) -> None:
    roots = [tmp_path / "a", tmp_path / "b"]
    barrier = threading.Barrier(2)
    observed: list[Path] = []
    lock = threading.Lock()

    def worker(root: Path) -> None:
        with reference_scope(root):
            barrier.wait(timeout=5)
            resolved = runtime_provenance_path()
            with lock:
                observed.append(resolved)

    threads = [threading.Thread(target=worker, args=(root,)) for root in roots]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert not any(thread.is_alive() for thread in threads)
    assert set(observed) == {_journal(root) for root in roots}


def test_missing_log_reads_empty_without_creating_directories(
    tmp_path: Path,
) -> None:
    assert read_reference_log(_journal(tmp_path)) == []
    assert read_provenance(tmp_path) == []
    assert not _journal(tmp_path).exists()
    assert not _journal(tmp_path).parent.exists()


def test_append_and_read_round_trip_is_pointer_only(tmp_path: Path) -> None:
    path = _journal(tmp_path)
    receipt = append_reference(path, _ref(), action="lookup")

    assert receipt["action"] == "lookup"
    assert receipt["stored_prose"] == 0
    assert len(receipt["sha256"]) == 64
    assert set(receipt) == {
        "action",
        "appid",
        "title",
        "url",
        "license",
        "dialect",
        "stored_prose",
        "sha256",
    }

    assert read_reference_log(path) == [receipt]
    assert path.stat().st_size <= provenance.MAX_RECORD_BYTES


def test_record_provenance_uses_explicit_workspace(tmp_path: Path) -> None:
    receipt = record_provenance(_ref(), action="lookup", root=tmp_path)

    assert read_provenance(tmp_path) == [receipt]
    assert _journal(tmp_path).is_file()


def test_record_provenance_uses_active_scope(tmp_path: Path) -> None:
    with reference_scope(tmp_path):
        receipt = record_provenance(_ref(), action="lookup")

    assert read_provenance(tmp_path) == [receipt]


def test_game_ref_port_restore_uses_caller_root_not_snapshot_data(
    tmp_path: Path,
) -> None:
    chosen = tmp_path / "trusted"
    hostile = tmp_path / "from-snapshot"
    snapshot = {
        "kind": "gameref",
        "slot": "left",
        "name": "restored",
        "root": str(hostile),
    }

    port = GameRefPort.from_snapshot(snapshot, root=chosen)

    assert port.slot == "left"
    assert port.name == "restored"
    assert port.root == chosen.resolve()


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("appid", True, "invalid appid"),
        ("appid", 0, "invalid appid"),
        ("title", "", "invalid title"),
        ("title", "x" * 513, "invalid title"),
        ("url", "", "invalid url"),
        ("license", "", "invalid license"),
        ("dialect", 3, "invalid dialect"),
    ],
)
def test_invalid_pointer_scalar_fails_before_persistence(
    tmp_path: Path,
    field: str,
    value: object,
    match: str,
) -> None:
    path = _journal(tmp_path)

    with pytest.raises((ReferenceProvenanceError, ValueError), match=match):
        append_reference(path, _ref(**{field: value}), action="lookup")

    assert not path.exists()


def test_blank_action_fails_before_persistence(tmp_path: Path) -> None:
    path = _journal(tmp_path)

    with pytest.raises(ReferenceProvenanceError, match="invalid action"):
        append_reference(path, _ref(), action="   ")

    assert not path.exists()


def test_reader_rejects_checksum_mismatch(tmp_path: Path) -> None:
    path = _journal(tmp_path)
    receipt = append_reference(path, _ref(), action="lookup")
    record = dict(receipt)
    record["title"] = "tampered"
    path.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(ReferenceProvenanceError, match="invalid provenance record 1"):
        read_reference_log(path)


def test_reader_rejects_duplicate_json_fields(tmp_path: Path) -> None:
    path = _journal(tmp_path)
    receipt = append_reference(path, _ref(), action="lookup")
    raw = json.dumps(receipt, sort_keys=True)
    raw = raw[:-1] + ',"action":"lookup"}\n'
    path.write_text(raw, encoding="utf-8")

    with pytest.raises(
        ReferenceProvenanceError,
        match="invalid provenance record 1",
    ):
        read_reference_log(path)


def test_reader_rejects_unknown_fields(tmp_path: Path) -> None:
    path = _journal(tmp_path)
    receipt = append_reference(path, _ref(), action="lookup")
    record = dict(receipt)
    record["unexpected"] = "field"
    path.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(ReferenceProvenanceError, match="invalid provenance record 1"):
        read_reference_log(path)


def test_reader_rejects_invalid_utf8(tmp_path: Path) -> None:
    path = _journal(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"\xff\n")

    with pytest.raises(
        ReferenceProvenanceError,
        match="invalid provenance record 1",
    ):
        read_reference_log(path)


def test_reader_rejects_incomplete_record(tmp_path: Path) -> None:
    path = _journal(tmp_path)
    append_reference(path, _ref(), action="lookup")
    raw = path.read_bytes()
    assert raw.endswith(b"\n")
    path.write_bytes(raw[:-1])

    with pytest.raises(ReferenceProvenanceError, match="incomplete record 1"):
        read_reference_log(path)


def test_writer_rejects_existing_incomplete_tail_without_repair(
    tmp_path: Path,
) -> None:
    path = _journal(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_bytes(b'{"partial":true}')

    with pytest.raises(
        ReferenceProvenanceError,
        match="journal has an incomplete tail",
    ):
        append_reference(path, _ref(), action="lookup")

    assert path.read_bytes() == b'{"partial":true}'


@pytest.mark.parametrize("bound", [0, -1, True, 100_001, 1.5, "10"])
def test_invalid_record_bound_is_rejected(
    tmp_path: Path,
    bound: object,
) -> None:
    with pytest.raises(
        ValueError,
        match="max_records must be an integer from 1 to 100000",
    ):
        read_reference_log(_journal(tmp_path), max_records=bound)  # type: ignore[arg-type]


def test_reader_enforces_record_count_budget(tmp_path: Path) -> None:
    path = _journal(tmp_path)
    append_reference(path, _ref(appid=1, title="one"), action="lookup")
    append_reference(path, _ref(appid=2, title="two"), action="lookup")

    with pytest.raises(
        ReferenceProvenanceError,
        match="journal budget exceeded at record 2",
    ):
        read_reference_log(path, max_records=1)


def test_reader_rejects_oversized_log_before_returning_records(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _journal(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"x" * 33)
    monkeypatch.setattr(provenance, "MAX_LOG_BYTES", 32)

    with pytest.raises(
        ReferenceProvenanceError,
        match="journal exceeds byte budget",
    ):
        read_reference_log(path)


def test_writer_rejects_log_budget_without_truncating_existing_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _journal(tmp_path)
    first = append_reference(path, _ref(appid=1, title="first"), action="lookup")
    before = path.read_bytes()
    monkeypatch.setattr(provenance, "MAX_LOG_BYTES", len(before))

    with pytest.raises(
        ReferenceProvenanceError,
        match="journal exceeds byte budget; archive it before continuing",
    ):
        append_reference(path, _ref(appid=2, title="second"), action="lookup")

    assert path.read_bytes() == before
    assert read_reference_log(path) == [first]


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlinks unsupported")
def test_reader_and_writer_reject_symlink_journal(tmp_path: Path) -> None:
    target = tmp_path / "target.jsonl"
    target.write_text("", encoding="utf-8")
    path = _journal(tmp_path)
    path.parent.mkdir(parents=True)
    path.symlink_to(target)

    with pytest.raises(ReferenceProvenanceError, match="journal must not be a symlink"):
        read_reference_log(path)
    with pytest.raises(ReferenceProvenanceError, match="journal must not be a symlink"):
        append_reference(path, _ref(), action="lookup")


def test_short_write_never_returns_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _journal(tmp_path)
    real_write = provenance.os.write

    def short_write(fd: int, data: bytes) -> int:
        written = real_write(fd, data[:-1])
        assert written == len(data) - 1
        return written

    monkeypatch.setattr(provenance.os, "write", short_write)

    with pytest.raises(OSError, match="incomplete provenance append"):
        append_reference(path, _ref(), action="lookup")

    assert path.exists()
    with pytest.raises(ReferenceProvenanceError, match="incomplete record 1"):
        read_reference_log(path)


def test_fsync_failure_propagates_and_preserves_verifiable_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _journal(tmp_path)

    def fail_fsync(_fd: int) -> None:
        raise OSError("fsync failed")

    monkeypatch.setattr(provenance.os, "fsync", fail_fsync)

    with pytest.raises(OSError, match="fsync failed"):
        append_reference(path, _ref(), action="lookup")

    records = read_reference_log(path)
    assert len(records) == 1
    assert records[0]["title"] == "Reference Fixture"
    assert records[0]["stored_prose"] == 0


def test_threaded_appends_are_serialized_and_all_records_verify(
    tmp_path: Path,
) -> None:
    path = _journal(tmp_path)
    count = 16
    barrier = threading.Barrier(count)
    errors: list[BaseException] = []

    def worker(index: int) -> None:
        try:
            barrier.wait(timeout=5)
            append_reference(
                path,
                _ref(appid=index + 1, title=f"ref-{index}"),
                action="lookup",
            )
        except BaseException as exc:  # pragma: no cover - asserted below
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(index,)) for index in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert errors == []
    assert not any(thread.is_alive() for thread in threads)

    records = read_reference_log(path)
    assert len(records) == count
    assert {record["appid"] for record in records} == set(range(1, count + 1))
    assert all(record["stored_prose"] == 0 for record in records)
