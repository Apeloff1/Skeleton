"""Regression tests for streaming journal reads and atomic compaction."""
import json
import os
import stat
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

from skeleton.organism import caps, journal


@pytest.fixture
def journal_file(tmp_path, monkeypatch):
    path = tmp_path / "journal.jsonl"
    monkeypatch.setattr(journal, "journal_path", lambda root=None: path)
    monkeypatch.setattr(caps, "live", lambda: SimpleNamespace(atoms=192))
    return path


def write_rows(path, count):
    with path.open("w", encoding="utf-8") as stream:
        for step in range(count):
            stream.write(json.dumps({"step": step}) + "\n")


def test_missing(journal_file):
    assert journal.tail() == []
    assert journal.trim() == 0
    assert not journal_file.exists()


@pytest.mark.parametrize("n, expected", [(2, [3, 4]), (0, [4]), (-5, [4]), (20, list(range(5)))])
def test_window(journal_file, n, expected):
    write_rows(journal_file, 5)
    assert [row["step"] for row in journal.tail(n)] == expected


def test_invalid_records_not_backfilled(journal_file):
    journal_file.write_text('{"step":1}\nnull\n[]\n42\n"x"\n{broken\n', encoding="utf-8")
    assert journal.tail(5) == []
    assert journal.tail(6) == [{"step": 1}]


def test_unicode_and_unterminated_line(journal_file):
    journal_file.write_bytes('{"topic":"café"}\r\n{"topic":"雪"}'.encode("utf-8"))
    assert journal.tail(2) == [{"topic": "café"}, {"topic": "雪"}]


def test_empty(journal_file):
    journal_file.touch()
    assert journal.tail() == []
    assert journal.trim() == 0


def test_no_whole_file_reads(journal_file, monkeypatch):
    write_rows(journal_file, 10000)

    def forbidden(*args, **kwargs):
        raise AssertionError("whole-file read")

    monkeypatch.setattr(Path, "read_text", forbidden)
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    assert journal.tail(2) == [{"step": 9998}, {"step": 9999}]
    assert journal.trim() == 9976
    assert journal.tail(100) == [{"step": i} for i in range(9976, 10000)]


def test_under_cap_no_replacement(journal_file, monkeypatch):
    write_rows(journal_file, 24)
    before = journal_file.read_bytes()

    def forbidden(*args):
        raise AssertionError("unexpected replacement")

    monkeypatch.setattr(journal.os, "replace", forbidden)
    assert journal.trim() == 0
    assert journal_file.read_bytes() == before


def test_compaction_idempotent(journal_file):
    write_rows(journal_file, 30)
    assert journal.trim() == 6
    assert journal.tail(30) == [{"step": i} for i in range(6, 30)]
    assert journal_file.read_bytes().endswith(b"\n")
    assert journal.trim() == 0
    assert not list(journal_file.parent.glob(".journal.jsonl.*.tmp"))


@pytest.mark.parametrize("operation", ["replace", "fsync", "chmod"])
def test_failed_compaction_preserves_original(journal_file, monkeypatch, operation):
    write_rows(journal_file, 30)
    before = journal_file.read_bytes()

    def fail(*args):
        raise OSError("injected failure")

    monkeypatch.setattr(journal.os, operation, fail)
    with pytest.raises(OSError, match="injected failure"):
        journal.trim()
    assert journal_file.read_bytes() == before
    assert not list(journal_file.parent.glob(".journal.jsonl.*.tmp"))


def test_publication_is_complete(journal_file, monkeypatch):
    write_rows(journal_file, 30)
    before = journal_file.read_bytes()
    replace = os.replace

    def inspect(source, destination):
        assert Path(source).parent == journal_file.parent
        assert Path(destination) == journal_file
        assert journal_file.read_bytes() == before
        rows = [json.loads(line) for line in Path(source).read_text(encoding="utf-8").splitlines()]
        assert rows == [{"step": i} for i in range(6, 30)]
        replace(source, destination)

    monkeypatch.setattr(journal.os, "replace", inspect)
    assert journal.trim() == 6


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
def test_permissions(journal_file):
    write_rows(journal_file, 30)
    journal_file.chmod(0o640)
    journal.trim()
    assert stat.S_IMODE(journal_file.stat().st_mode) == 0o640


def test_caps_fallback(journal_file, monkeypatch):
    def fail():
        raise RuntimeError("unavailable")

    monkeypatch.setattr(caps, "live", fail)
    write_rows(journal_file, 100)
    assert journal.trim() == 20
    assert len(journal.tail(100)) == 80


def test_append_schema_and_cap(journal_file):
    write_rows(journal_file, 24)
    result = journal.append({"step": 24, "topic": "test", "stored_prose": 99, "extra": "ignored"})
    assert result == {"path": str(journal_file), "appended": 1}
    rows = journal.tail(100)
    assert len(rows) == 24
    assert rows[0] == {"step": 1}
    assert rows[-1] == {
        "step": 24, "G": None, "decision": None, "topic": "test",
        "coverage": None, "pressure": None, "stored_prose": 0,
    }


def test_threaded_appends(journal_file, monkeypatch):
    monkeypatch.setattr(caps, "live", lambda: SimpleNamespace(atoms=8000))
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda step: journal.append({"step": step}), range(100)))
    rows = journal.tail(1000)
    assert len(rows) == 100
    assert {row["step"] for row in rows} == set(range(100))
