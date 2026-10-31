"""Full-book text -> reviewed Jeeves training intake, with source-span receipts.

The existing project-disjoint corpus builder and checkpoint-pinned optimizer
are used for weights. This component never invents training outcomes, fetches
books, changes serving weights or bypasses rights and quality review.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any

from .jeeves_game_corpus import FAMILIES, _check_rights, _ID, _text
from .jeeves_game_corpus_builder import INTAKE_SCHEMA, MAX_INTAKE_EXAMPLES
from .jeeves_production_game_train import ProductionCheckpointError, _strict_json

SCHEMA = "skeleton.jeeves.book_weight_intake.v1"
RECEIPT = "skeleton.jeeves.book_weight_coverage.v1"
SHA = re.compile(r"[0-9a-f]{64}\Z")


def _json(obj: Any) -> bytes:
    try:
        return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode()
    except (TypeError, ValueError, RecursionError, OverflowError) as exc:
        raise ProductionCheckpointError("Unserializable book training evidence") from exc


def _sha(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def _id(raw: Any) -> str:
    if not isinstance(raw, str) or not _ID.fullmatch(raw):
        raise ProductionCheckpointError("Book/chapter ID is not a safe training identifier")
    return raw


def _spans(text: Any, size: int):
    if (not isinstance(text, str) or not 100 <= len(text) <= 2_000_000
            or text.isspace() or any(ord(c) < 32 and c not in "\t\r\n" for c in text)):
        raise ProductionCheckpointError("Chapter text must be complete bounded plain text")
    if type(size) is not int or not 128 <= size <= 4096:
        raise ProductionCheckpointError("Segment size must be 128..4096")
    offset = 0
    while offset < len(text):
        stop = min(offset + size, len(text))
        if 0 < len(text) - stop < 20:
            stop = len(text)
        piece = text[offset:stop]
        if not piece.strip() or len(piece) < 20:
            raise ProductionCheckpointError("Whitespace-only or very short text segment")
        yield offset, stop, piece
        offset = stop


def compile_books(source: dict[str, Any], size: int = 2048) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Cover every character of supplied full text and preserve training lineage.

    Text spans are next-target material, *not* a claim of game-development
    competence. The separately held out game benchmark is not trained upon.
    """
    if not isinstance(source, dict) or source.get("schema_version") != SCHEMA:
        raise ProductionCheckpointError("Unknown book-corpus schema")
    books = source.get("books")
    if not isinstance(books, list) or not 1 <= len(books) <= 512:
        raise ProductionCheckpointError("Book batch must contain 1..512 volumes")
    rows = []
    receipts = []
    book_ids: set[str] = set()
    chapters_count = 0
    prev = "0" * 64
    for book in books:
        if not isinstance(book, dict):
            raise ProductionCheckpointError("Book must be an object")
        book_id = _id(book.get("book_id"))
        if book_id in book_ids:
            raise ProductionCheckpointError("Duplicate book ID")
        book_ids.add(book_id)
        title = _text(book.get("title"), label="book title", minimum=3, maximum=160)
        rights = book.get("rights")
        _check_rights({"rights": rights})
        review = book.get("review")
        if (not isinstance(review, dict) or review.get("quality_approved") is not True
                or not isinstance(review.get("reviewer_id"), str)
                or not 3 <= len(review["reviewer_id"].strip()) <= 128
                or not isinstance(review.get("note"), str)
                or len(review["note"].strip()) < 24):
            raise ProductionCheckpointError("Book requires real human quality and rights review")
        chapters = book.get("chapters")
        if not isinstance(chapters, list) or not 1 <= len(chapters) <= 4096:
            raise ProductionCheckpointError("Book has no complete chapter list")
        seen: set[str] = set()
        for chapter in chapters:
            if not isinstance(chapter, dict):
                raise ProductionCheckpointError("Chapter must be an object")
            name = _id(chapter.get("chapter_id"))
            if name in seen:
                raise ProductionCheckpointError("Duplicate chapter ID")
            seen.add(name)
            family = chapter.get("family")
            if family not in FAMILIES:
                raise ProductionCheckpointError("Chapter must map to existing eight-domain curriculum")
            content = chapter.get("text")
            chapter_digest = _sha(content.encode("utf-8")) if isinstance(content, str) else ""
            last = 0
            chapters_count += 1
            for index, (start, end, part) in enumerate(_spans(content, size)):
                if start != last or part != content[start:end]:
                    raise ProductionCheckpointError("Full-text coverage mismatch")
                last = end
                identifier = f"{book_id}.{name}.{index:05d}"
                _id(identifier)
                prompt = (f"Study approved game-development reference '{title}' "
                          f"chapter {name}, passage {index}; reconstruct its content faithfully "
                          "while preserving source identity and authored context.")
                row = {"schema_version": INTAKE_SCHEMA, "id": identifier,
                       "source_project_id": book_id, "family": family,
                       "prompt": prompt, "answer": part, "rights": rights,
                       "quality_reviewer_id": review["reviewer_id"].strip(),
                       "quality_approved": True, "quality_review_note": review["note"].strip()}
                _text(prompt, label="prompt", minimum=10, maximum=4096)
                _text(part, label="answer", minimum=20, maximum=12000)
                rows.append(row)
                record = {"book_id": book_id, "chapter_id": name,
                          "chapter_sha256": chapter_digest, "start": start, "end": end,
                          "span_sha256": _sha(part.encode("utf-8")),
                          "record_id": identifier, "record_sha256": _sha(_json(row))}
                prev = _sha(_json({"prior": prev, "record": record}))
                receipts.append({**record, "chain_sha256": prev})
                if len(rows) > MAX_INTAKE_EXAMPLES:
                    raise ProductionCheckpointError("Batch exceeds canonical 10000-example quota; shard by whole books")
            if last != len(content):
                raise ProductionCheckpointError("Incomplete source chapter")
    proof = {"schema_version": RECEIPT, "book_count": len(books),
             "chapter_count": chapters_count, "record_count": len(rows),
             "source_sha256": _sha(_json(source)), "chain_sha256": prev,
             "coverage": "all source characters represented exactly by contiguous ordered spans",
             "segments": receipts, "training_started": False,
             "rights_review_is_operator_attestation": True, "model_promoted": False}
    return rows, proof


def publish(*, source: Path, expected_source_sha256: str, intake: Path,
            coverage: Path, segment_chars: int = 2048) -> dict[str, Any]:
    """Safely publish candidate dataset intake and proof, never overwrite."""
    if not isinstance(expected_source_sha256, str) or not SHA.fullmatch(expected_source_sha256):
        raise ProductionCheckpointError("Require independent SHA-256 of reviewed book source")
    if source.is_symlink() or not source.is_file() or not 16 <= source.stat().st_size <= 64 * 1024 * 1024:
        raise ProductionCheckpointError("Source must be a bounded regular file")
    raw = source.read_bytes()
    if _sha(raw) != expected_source_sha256:
        raise ProductionCheckpointError("Book content changed after review")
    if (intake.resolve() == coverage.resolve() or intake.parent.resolve() != coverage.parent.resolve()
            or any(path.exists() or path.is_symlink() or not path.parent.is_dir()
                   for path in (intake, coverage))):
        raise ProductionCheckpointError("Outputs must be distinct, new, and in one existing directory")
    rows, report = compile_books(_strict_json(raw), segment_chars)
    intake_bytes = b"".join(_json(row) + b"\n" for row in rows)
    report["intake_sha256"] = _sha(intake_bytes)
    report_bytes = _json(report) + b"\n"
    if len(intake_bytes) > 64 * 1024 * 1024 or len(report_bytes) > 8 * 1024 * 1024:
        raise ProductionCheckpointError("Corpus or receipt exceeds bounded output budget")
    with tempfile.TemporaryDirectory(prefix=".books-", dir=intake.parent) as tmp:
        staged = (Path(tmp) / "intake", Path(tmp) / "coverage")
        for path, data in zip(staged, (intake_bytes, report_bytes)):
            with path.open("xb") as fd:
                fd.write(data)
                fd.flush()
                os.fsync(fd.fileno())
            os.chmod(path, 0o600)
        installed = []
        try:
            for path, target in zip(staged, (intake, coverage)):
                os.link(path, target)
                installed.append(target)
        except BaseException:
            for target in installed:
                target.unlink(missing_ok=True)
            raise
    return {"status": "reviewed_book_training_intake_published",
            "books": report["book_count"], "chapters": report["chapter_count"],
            "examples": report["record_count"], "intake_sha256": report["intake_sha256"],
            "coverage_sha256": _sha(report_bytes), "chain_sha256": report["chain_sha256"],
            "training_started": False, "production_weights_modified": False,
            "next": "canonical jeeves_game_corpus_builder then jeeves_production_game_train"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--intake", required=True, type=Path)
    parser.add_argument("--coverage", required=True, type=Path)
    parser.add_argument("--segment-chars", type=int, default=2048)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(publish(source=args.source, expected_source_sha256=args.expected_sha256,
                                 intake=args.intake, coverage=args.coverage,
                                 segment_chars=args.segment_chars), sort_keys=True))
        return 0
    except (OSError, ValueError, TypeError, RuntimeError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)[:400]}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
