"""Local memory, office, media, and multi-turn desk tools. No model is bound."""

from __future__ import annotations

import asyncio
import importlib.util
import shutil
import sys
from pathlib import Path

import pytest

from skeleton.local_ai import (
    docx_ops,
    ffmpeg_ops,
    memory_edit,
    pdf_ops,
    pptx_ops,
    xlsx_ops,
)
from skeleton.local_ai.ffmpeg_ops import MediaRejected, plan_media, process
from skeleton.local_ai.memory_book import MemoryBook, MemoryRejected
from skeleton.local_ai.multi_turn import MultiTurnDesk, TurnRejected
from skeleton.local_ai.office_pack import OfficeRejected, build_pdf, read_pdf


def test_memory_remember_replace_forget_reload(tmp_path: Path) -> None:
    path = tmp_path / "memory.md"
    book = MemoryBook(path)
    book.remember("Alpha fact")
    book.remember("ALPHA FACT")
    book.remember("Beta fact")
    assert book.facts() == ["Alpha fact", "Beta fact"]
    book.replace("alpha fact", "Alpha updated")
    book.forget("beta fact")
    rendered = book.render()
    assert rendered.startswith("# Memory\n")
    assert "- Alpha updated\n" in rendered
    assert "Beta" not in rendered
    assert list(path.parent.glob(".memory.*.tmp")) == []

    reloaded = MemoryBook(path)
    assert reloaded.facts() == ["Alpha updated"]
    assert reloaded.search("updated") == ["Alpha updated"]
    assert reloaded.search("missing term") == []
    assert (path.read_bytes()).startswith(b"# Memory\n")
    assert path.stat().st_size <= 64 * 1024


def test_memory_rejects_empty_type_length_and_secrets(tmp_path: Path) -> None:
    book = MemoryBook(tmp_path / "memory.md")
    book.remember("the token bucket is full")
    before = (tmp_path / "memory.md").read_bytes()
    for secret in (
        "api_key=abcd",
        "api-key: abcd",
        "apikey=abcd",
        "API_KEY = abcd",
        "secret=abcd",
        "password: hunter2",
        "token=abcd",
        "bearer: abcd",
        "not api_key=abcd",
    ):
        with pytest.raises(MemoryRejected):
            book.remember(secret)
    assert book.facts() == ["the token bucket is full"]
    assert (tmp_path / "memory.md").read_bytes() == before
    for bad in ("", "   ", None, 5, b"text", "a" * 501):
        with pytest.raises(MemoryRejected):
            book.remember(bad)  # type: ignore[arg-type]
    book.remember("a" * 500)
    assert book.facts()[-1] == "a" * 500


def test_memory_negation_drops_positive_then_stores_it(tmp_path: Path) -> None:
    book = MemoryBook(tmp_path / "memory.md")
    book.remember("The Door Is Open")
    book.remember("notice the bell")
    book.remember("not the door is open")
    assert book.facts() == ["notice the bell", "not the door is open"]
    book.remember("NOT the door is open")
    assert book.facts() == ["notice the bell", "not the door is open"]
    reloaded = MemoryBook(tmp_path / "memory.md")
    assert reloaded.search("door") == ["not the door is open"]


def test_memory_file_cap(tmp_path: Path) -> None:
    book = MemoryBook(tmp_path / "memory.md")
    rejected = False
    for index in range(140):
        fact = f"{index:03d}" + ("k" * 497)
        try:
            book.remember(fact)
        except MemoryRejected:
            rejected = True
            break
    assert rejected
    assert len(book.facts()) == 130
    assert (tmp_path / "memory.md").stat().st_size <= 64 * 1024


def test_store_uses_process_local_book() -> None:
    fact = "the kettle on this local desk is warm"
    assert memory_edit.store(fact) is None
    assert memory_edit.book() is memory_edit.book()
    assert fact in memory_edit.book().facts()
    with pytest.raises(MemoryRejected):
        memory_edit.store("token=local")


def test_office_round_trip() -> None:
    pdf = pdf_ops.generate(2)
    assert isinstance(pdf, bytes)
    assert pdf.startswith(b"%PDF")
    assert b"(Page 1) Tj" in pdf
    assert b"(Page 2) Tj" in pdf
    assert pdf_ops.read_text(pdf) == ["Page 1", "Page 2"]
    with pytest.raises(OfficeRejected):
        pdf_ops.generate(True)
    with pytest.raises(OfficeRejected):
        pdf_ops.generate(False)
    with pytest.raises(OfficeRejected):
        pdf_ops.generate(33)

    special = build_pdf(["A (B) \\ C", "café"])
    assert b"(A \\(B\\) \\\\ C) Tj" in special
    assert read_pdf(special) == ["A (B) \\ C", "café"]

    paragraphs = ["Hello", "A & B <C>", "café"]
    document = docx_ops.create_doc(paragraphs)
    assert b"word/document.xml" in document
    assert b"w:t" in _zip_part(document, "word/document.xml")
    assert docx_ops.read_paragraphs(document) == paragraphs
    with pytest.raises(OfficeRejected):
        docx_ops.create_doc(["a"] * 33)
    with pytest.raises(OfficeRejected):
        docx_ops.create_doc("Hello")  # type: ignore[arg-type]

    slides = ["Opening", "A & B", "café"]
    deck = pptx_ops.create_deck(slides)
    slide = _zip_part(deck, "ppt/slides/slide1.xml")
    assert b"a:t" in slide
    assert pptx_ops.read_slides(deck) == slides
    with pytest.raises(OfficeRejected):
        pptx_ops.create_deck(["s"] * 33)

    rows = [["North", "A & B"], ["café", "South"]]
    workbook = xlsx_ops.create_workbook(rows)
    sheet = _zip_part(workbook, "xl/worksheets/sheet1.xml")
    assert b"inlineStr" in sheet
    assert xlsx_ops.read_rows(workbook) == rows
    with pytest.raises(OfficeRejected):
        xlsx_ops.create_workbook([["x"] * 27])
    with pytest.raises(OfficeRejected):
        xlsx_ops.create_workbook([["x"]] * 201)
    with pytest.raises(OfficeRejected):
        xlsx_ops.create_workbook([["x" * 4001]])


def test_media_rejects_shell_and_path_escape(tmp_path: Path) -> None:
    root = tmp_path / "desk"
    root.mkdir()
    clip = root / "clip.wav"
    clip.write_bytes(b"RIFF")
    outside = tmp_path / "outside.wav"
    outside.write_bytes(b"RIFF")
    alias = root / "alias.wav"
    alias.symlink_to(outside)

    for command in (
        "probe clip.wav; rm -rf /",
        "convert a | b",
        "plan clip.wav && id",
        "inspect `id`",
        "trim $(id)",
        "probe clip.wav\nconvert other.wav",
        "convert ../clip.wav",
        "probe foo/../../etc/passwd",
        "trim -to clip.wav",
        "inspect clip.wav -hide_banner",
        f"probe {outside}",
        "probe alias.wav",
    ):
        with pytest.raises(MediaRejected):
            plan_media(command, root=root)
        with pytest.raises(MediaRejected):
            process(command, root=root)

    planned = plan_media("plan clip.wav", root=root)
    assert planned.executed is False
    assert planned.shell is False
    assert planned["verb"] == "plan"
    converted = process("convert clip.wav", root=root)
    assert converted.executed is False
    assert converted.shell is False
    unbound = process("probe clip.wav")
    assert unbound.executed is False
    assert unbound.shell is False
    extra = process("probe clip.wav other.wav", root=root)
    assert extra.executed is False
    assert extra.shell is False

    probed = ffmpeg_ops.process("probe clip.wav", root=root)
    assert probed.shell is False
    if shutil.which("ffprobe"):
        assert probed.executed is True
        assert isinstance(probed.returncode, int)
    else:
        assert probed.executed is False


def test_eight_turn_desk_never_calls_a_model(tmp_path: Path) -> None:
    desk = MultiTurnDesk(tmp_path)
    missed = desk.run(["ask notes device"])
    assert missed.model_called is False
    assert missed.turns[0].answer == "No note on this desk matches. No model is bound."
    split = desk.run(
        [
            "remember notes live in the drawer",
            "remember the device is unplugged",
            "ask notes device",
        ]
    )
    assert split.turns[-1].answer == "No note on this desk matches. No model is bound."
    assert split.model_called is False

    root = tmp_path / "session"
    desk = MultiTurnDesk(root)
    result = desk.run(
        [
            "remember The notes device is on the desk",
            "ask notes device",
            "pdf Alpha | Beta",
            "docx First paragraph | A & B",
            "deck Opening | Closing",
            "xlsx North | South",
            "media plan room.wav",
            "forget The notes device is on the desk",
        ]
    )
    assert result.model_called is False
    assert result["model_called"] is False
    assert result.memory_count == 0
    assert all(turn.model_called is False for turn in result.turns)
    assert [turn.status for turn in result.turns] == ["ok"] * 8
    assert result.turns[1].answer == "The notes device is on the desk"
    assert pdf_ops.read_text((root / "notes.pdf").read_bytes()) == ["Alpha", "Beta"]
    assert b"(Alpha) Tj" in (root / "notes.pdf").read_bytes()
    assert docx_ops.read_paragraphs((root / "notes.docx").read_bytes()) == [
        "First paragraph",
        "A & B",
    ]
    assert pptx_ops.read_slides((root / "notes.pptx").read_bytes()) == ["Opening", "Closing"]
    assert xlsx_ops.read_rows((root / "notes.xlsx").read_bytes()) == [["North"], ["South"]]
    assert result.turns[6].executed is False
    assert result.turns[6].shell is False
    assert desk.memory.facts() == []

    refused = desk.run(["remember api_key=nope", "remember a plain note"])
    assert refused.turns[0].status == "refused"
    assert refused.turns[1].status == "ok"
    assert refused.model_called is False
    assert refused.memory_count == 1


def test_empty_run_and_unknown_verb_raise(tmp_path: Path) -> None:
    desk = MultiTurnDesk(tmp_path)
    with pytest.raises(TurnRejected):
        desk.run([])
    with pytest.raises(TurnRejected):
        desk.run(["dance now"])
    assert desk.memory.facts() == []


def test_transcription_sidecar_and_missing_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_recording_ledger()
    provider = module.TranscriptionProvider()
    wav = tmp_path / "room.wav"
    wav.write_bytes(b"RIFF")
    (tmp_path / "room.wav.txt").write_text("  The door sticks. \n", encoding="utf-8")
    assert asyncio.run(provider.transcribe(str(wav))) == "The door sticks."

    bare = tmp_path / "quiet.wav"
    bare.write_bytes(b"RIFF")
    assert asyncio.run(provider.transcribe(str(bare))) == ""

    stem_dir = tmp_path / "stem"
    stem_dir.mkdir()
    stem_wav = stem_dir / "room.wav"
    stem_wav.write_bytes(b"RIFF")
    (stem_dir / "room.txt").write_text("same stem\n", encoding="utf-8")
    assert asyncio.run(provider.transcribe(str(stem_wav))) == "same stem"

    linked = tmp_path / "linked.wav"
    linked.symlink_to(wav)
    (tmp_path / "linked.wav.txt").write_text("should not be read", encoding="utf-8")
    assert asyncio.run(provider.transcribe(str(linked))) == ""

    sidecar = tmp_path / "skip.wav.txt"
    sidecar.symlink_to(tmp_path / "room.wav.txt")
    skipped = tmp_path / "skip.wav"
    skipped.write_bytes(b"RIFF")
    assert asyncio.run(provider.transcribe(str(skipped))) == ""

    monkeypatch.setenv("GAMEFORGE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GAMEFORGE_ALWAYS_ON_RECORDING", "1")
    service = module.RecordingLedgerService(user_id="user", enabled=True)
    service.set_consent(True)
    accepted = asyncio.run(service.ingest_audio_file(str(wav)))
    assert accepted["transcribed"] is True
    assert service._chunks[0].transcribed is True
    empty = asyncio.run(service.ingest_audio_file(str(bare)))
    assert empty["transcribed"] is False
    assert service._chunks[1].transcribed is False


def _load_recording_ledger():
    path = Path(__file__).resolve().parents[2] / "backend/gameforge/personal/logs/recording_ledger.py"
    spec = importlib.util.spec_from_file_location("recording_ledger_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _zip_part(package: bytes, name: str) -> bytes:
    import io
    import zipfile

    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        return archive.read(name)
