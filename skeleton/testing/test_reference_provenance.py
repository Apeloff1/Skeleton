import hashlib
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from skeleton.cortex import reference_provenance as journal
from skeleton.cortex import refs


def reference():
    return refs.index()[0]


def test_lookup_uses_runtime_state_and_preserves_packaged_corpus(tmp_path, monkeypatch):
    from skeleton.cortex.acquire_repo import acquired_dir
    corpus = acquired_dir() / "gaming" / "provenance.jsonl"
    before = corpus.read_bytes()
    monkeypatch.chdir(tmp_path)
    expected = tmp_path / ".skeleton/references/provenance.jsonl"
    assert refs.provenance_path() == expected
    assert not expected.parent.exists()
    assert refs.read_provenance() == []
    result = refs.refer("like elden ring")
    assert refs.read_provenance() == [result["provenance"]]
    assert corpus.read_bytes() == before
    assert not (tmp_path / "skeleton").exists()


def test_legacy_checksum_format_round_trips_without_prose(tmp_path):
    pointer = refs.record_provenance(reference(), action="lookup", root=tmp_path)
    unsigned = {k: v for k, v in pointer.items() if k != "sha256"}
    assert pointer["sha256"] == hashlib.sha256(json.dumps(unsigned, sort_keys=True).encode()).hexdigest()
    assert refs.read_provenance(tmp_path) == [pointer]
    assert set(pointer) == {"action", "appid", "title", "url", "license", "dialect", "stored_prose", "sha256"}


def test_nested_scope_restores_outer_root_after_failure(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    default = refs.provenance_path()
    with refs.reference_scope(tmp_path / "outer"):
        refs.refer("hades")
        with pytest.raises(RuntimeError), refs.reference_scope(tmp_path / "inner"):
            refs.refer("hollow knight")
            raise RuntimeError("test")
        refs.refer("elden ring")
        refs.refer("hades", root=tmp_path / "explicit")
    assert refs.provenance_path() == default
    assert not default.exists()
    assert len(refs.read_provenance(tmp_path / "outer")) == 2
    assert len(refs.read_provenance(tmp_path / "inner")) == 1
    assert len(refs.read_provenance(tmp_path / "explicit")) == 1


def test_concurrent_scopes_and_threaded_appends_are_isolated(tmp_path):
    def write(index):
        with refs.reference_scope(tmp_path / str(index % 2)):
            return refs.record_provenance(reference(), action=f"lookup-{index}")
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(write, range(40)))
    for group in (0, 1):
        rows = refs.read_provenance(tmp_path / str(group))
        assert {r["sha256"] for r in rows} == {r["sha256"] for i, r in enumerate(results) if i % 2 == group}
        assert len(rows) == 20


def test_port_restore_requires_caller_storage_not_snapshot_storage(tmp_path):
    port = refs.GameRefPort(name="references", root=tmp_path / "first")
    port.think("hades", {"root": str(tmp_path / "untrusted")})
    snapshot = {**port.snapshot(), "root": str(tmp_path / "untrusted")}
    restored = refs.GameRefPort.from_snapshot(snapshot, root=tmp_path / "second")
    assert restored.name == port.name
    restored.think("elden ring", {})
    assert len(refs.read_provenance(tmp_path / "first")) == 1
    assert len(refs.read_provenance(tmp_path / "second")) == 1
    assert not (tmp_path / "untrusted").exists()
    assert "root" not in port.snapshot()


def test_async_scopes_do_not_leak_across_interleaved_tasks(tmp_path):
    import asyncio

    async def observe(name):
        with refs.reference_scope(tmp_path / name):
            await asyncio.sleep(0)
            refs.record_provenance(reference(), action=name)
            await asyncio.sleep(0)
            assert refs.read_provenance()[0]["action"] == name

    async def run():
        await asyncio.gather(observe("first"), observe("second"))

    asyncio.run(run())
    assert len(refs.read_provenance(tmp_path / "first")) == 1
    assert len(refs.read_provenance(tmp_path / "second")) == 1


@pytest.mark.parametrize("field,value", [("appid", True), ("appid", -1), ("appid", "1"),
    ("title", "x" * 513), ("url", []), ("license", ""), ("dialect", 42), ("api_key", "sensitive")])
def test_invalid_reference_never_creates_state(tmp_path, field, value):
    with pytest.raises(ValueError):
        refs.record_provenance({**reference(), field: value}, action="lookup", root=tmp_path)
    assert not (tmp_path / ".skeleton").exists()


@pytest.mark.parametrize("action", [None, "", "x" * 65, 7])
def test_invalid_action_never_creates_state(tmp_path, action):
    with pytest.raises(journal.ReferenceProvenanceError):
        refs.record_provenance(reference(), action=action, root=tmp_path)
    assert not (tmp_path / ".skeleton").exists()


@pytest.mark.parametrize("damage", ["checksum", "extra", "duplicate", "truncated", "utf8", "array", "blank"])
def test_reader_rejects_corruption_without_returning_a_valid_prefix(tmp_path, damage):
    good = refs.record_provenance(reference(), action="lookup", root=tmp_path)
    path = refs.provenance_path(tmp_path)
    bad = dict(good)
    if damage == "checksum":
        bad["title"] = "sensitive test payload"
    if damage == "extra":
        bad["unknown"] = "sensitive test payload"
    line = (json.dumps(bad) + "\n").encode()
    if damage == "duplicate":
        line = b'{"action":"duplicate",' + line[1:]
    if damage == "truncated":
        line = line[:-1]
    if damage == "utf8":
        line = b"\xff\n"
    if damage == "array":
        line = b"[]\n"
    if damage == "blank":
        line = b"\n"
    with path.open("ab") as handle:
        handle.write(line)
    before = path.read_bytes()
    with pytest.raises(journal.ReferenceProvenanceError) as error:
        refs.read_provenance(tmp_path)
    assert "sensitive test payload" not in str(error.value)
    assert path.read_bytes() == before


def test_torn_append_is_preserved_and_further_appends_fail(tmp_path, monkeypatch):
    original = journal.os.write
    with monkeypatch.context() as patch:
        patch.setattr(journal.os, "write", lambda fd, data: original(fd, data[:7]))
        with pytest.raises(OSError, match="incomplete"):
            refs.record_provenance(reference(), action="lookup", root=tmp_path)
    path = refs.provenance_path(tmp_path)
    before = path.read_bytes()
    with pytest.raises(journal.ReferenceProvenanceError, match="incomplete tail"):
        refs.record_provenance(reference(), action="lookup", root=tmp_path)
    assert path.read_bytes() == before
    with pytest.raises(journal.ReferenceProvenanceError):
        refs.read_provenance(tmp_path)


def test_sync_failure_never_returns_a_successful_receipt(tmp_path, monkeypatch):
    def fail(fd):
        raise OSError("sync failed")
    monkeypatch.setattr(journal.os, "fsync", fail)
    with pytest.raises(OSError, match="sync failed"):
        refs.record_provenance(reference(), action="lookup", root=tmp_path)
    # The append outcome is uncertain to the caller, not automatically retried.
    assert len(refs.read_provenance(tmp_path)) == 1


def test_record_count_line_and_total_byte_budgets_fail_closed(tmp_path, monkeypatch):
    refs.record_provenance(reference(), action="lookup", root=tmp_path)
    refs.record_provenance(reference(), action="lookup", root=tmp_path)
    path = refs.provenance_path(tmp_path)
    before = path.read_bytes()
    with pytest.raises(journal.ReferenceProvenanceError, match="budget"):
        refs.read_provenance(tmp_path, max_records=1)
    with monkeypatch.context() as patch:
        patch.setattr(journal, "MAX_RECORD_BYTES", 16)
        with pytest.raises(journal.ReferenceProvenanceError, match="budget"):
            refs.read_provenance(tmp_path)
    monkeypatch.setattr(journal, "MAX_LOG_BYTES", len(before))
    with pytest.raises(journal.ReferenceProvenanceError, match="budget"):
        refs.record_provenance(reference(), action="lookup", root=tmp_path)
    assert path.read_bytes() == before
    monkeypatch.setattr(journal, "MAX_LOG_BYTES", len(before) - 1)
    with pytest.raises(journal.ReferenceProvenanceError, match="budget"):
        refs.read_provenance(tmp_path)


def test_unreadable_journal_is_not_treated_as_absent(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise PermissionError("test")
    monkeypatch.setattr(journal, "_open_log", fail)
    with pytest.raises(PermissionError):
        refs.read_provenance(tmp_path)


def test_stream_budget_is_enforced_even_when_initial_size_is_stale(tmp_path, monkeypatch):
    from types import SimpleNamespace
    refs.record_provenance(reference(), action="lookup", root=tmp_path)
    size = refs.provenance_path(tmp_path).stat().st_size
    original = journal.os.fstat

    def stale(fd):
        actual = original(fd)
        return SimpleNamespace(st_mode=actual.st_mode, st_dev=actual.st_dev,
                               st_ino=actual.st_ino, st_size=0)

    monkeypatch.setattr(journal, "MAX_LOG_BYTES", size - 1)
    monkeypatch.setattr(journal.os, "fstat", stale)
    with pytest.raises(journal.ReferenceProvenanceError, match="budget"):
        refs.read_provenance(tmp_path)


def test_deck_nested_reference_operations_stay_in_selected_workspace(tmp_path, monkeypatch):
    from skeleton.cortex.deck import CommandDeck
    monkeypatch.chdir(tmp_path)

    class Model:
        def ascend(self, stimulus):
            return refs.refer(stimulus)

    deck = CommandDeck(neo=Model(), root=tmp_path / "deck")
    assert deck.speak("elden ring")["hit"] == 1
    assert deck.plan("hades")["hit"] == 1
    rows = refs.read_provenance(tmp_path / "deck")
    assert len(rows) >= 3
    assert not refs.provenance_path().exists()


def test_symlink_journal_is_rejected(tmp_path):
    target = tmp_path / "target"
    target.write_text("unchanged", encoding="utf-8")
    path = refs.provenance_path(tmp_path)
    path.parent.mkdir(parents=True)
    try:
        path.symlink_to(target)
    except OSError as exc:
        if getattr(exc, "winerror", None) == 1314:
            pytest.skip("host lacks symlink privilege")
        raise
    with pytest.raises((journal.ReferenceProvenanceError, OSError)):
        refs.record_provenance(reference(), action="lookup", root=tmp_path)
    with pytest.raises((journal.ReferenceProvenanceError, OSError)):
        refs.read_provenance(tmp_path)
    assert target.read_text(encoding="utf-8") == "unchanged"
