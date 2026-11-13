"""Rights-reviewed complete-book intake for the EXISTING Jeeves weight trainer.

This compiler does NOT pretend a JSONL file is model training. It preserves
every admitted source character in ordered chunks, emits source/segment SHA256
receipts, and produces the exact reviewed-intake schema consumed by
jeeves_game_corpus_builder. The latter creates leak-resistant train/eval
manifests for jeeves_production_game_train. Never silently train on scraped,
unknown-rights, or reviewer-unapproved books.

Full-book admission may require multiple shards; no source text is truncated to
fit a model context or the current candidate trainer's finite input window.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from typing import Any

from .jeeves_game_corpus import FAMILIES, RIGHTS_SCHEMA
from .jeeves_game_corpus_builder import INTAKE_SCHEMA

SCHEMA = "skeleton.jeeves.book_weights_intake.v1"
MAX_SOURCE_BYTES = 64 * 1024 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024
CHUNK_CHARS = 7_500
MAX_SHARD_ROWS = 1000
ALLOWED_KINDS = frozenset(("original_authoring", "licensed_training", "public_domain"))
TOKEN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{2,127}$")
HEX = re.compile(r"^[a-f0-9]{64}$")


class BookIntakeError(ValueError):
    """Book, license, reviewer or byte coverage could not be proven."""


def _encode(value: object) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=True,
                          separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (ValueError, TypeError) as exc:
        raise BookIntakeError("noncanonical manifest or receipt") from exc


def _sha(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def _id(value: object, label: str) -> str:
    if not isinstance(value, str) or not TOKEN.fullmatch(value):
        raise BookIntakeError(f"{label} requires a stable 3..128 character identifier")
    return value


def _text(value: object, label: str, *, least: int, most: int = 4096) -> str:
    if not isinstance(value, str) or not least <= len(value.strip()) <= most:
        raise BookIntakeError(f"{label} must contain {least}..{most} characters")
    return value.strip()


def _regular(path: Path, *, max_bytes: int) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise BookIntakeError("book source must be a regular non-symlink file")
    size = path.stat().st_size
    if not 1 <= size <= max_bytes:
        raise BookIntakeError("book source outside admitted file limits")
    raw = path.read_bytes()
    if len(raw) != size:
        raise BookIntakeError("book source changed while being read")
    return raw


def _book_rights(book: dict[str, Any]) -> dict[str, object]:
    rights = book.get("rights")
    if not isinstance(rights, dict) or rights.get("schema_version") != RIGHTS_SCHEMA:
        raise BookIntakeError("book lacks the canonical source-rights statement")
    if rights.get("source_kind") not in ALLOWED_KINDS or rights.get("training_permitted") is not True:
        raise BookIntakeError("full book is not authorized for weight training")
    for field in ("rights_holder", "rights_basis", "review_id"):
        _text(rights.get(field), f"rights.{field}", least=3, most=512)
    if (rights["source_kind"] == "licensed_training"
            and not rights["rights_basis"].startswith("license:")):
        raise BookIntakeError("licensed book needs an explicit license reference")
    return dict(rights)


def _load_manifest(path: Path) -> tuple[dict[str, Any], bytes]:
    source = _regular(path, max_bytes=MAX_MANIFEST_BYTES)
    def pairs(entries: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in entries:
            if key in result:
                raise BookIntakeError("duplicate manifest property")
            result[key] = value
        return result
    try:
        parsed = json.loads(source, object_pairs_hook=pairs,
                            parse_constant=lambda _: (_ for _ in ()).throw(
                                BookIntakeError("nonfinite manifest number")))
    except (ValueError, UnicodeDecodeError, RecursionError) as exc:
        raise BookIntakeError("unreadable book manifest") from exc
    if not isinstance(parsed, dict) or parsed.get("schema_version") != SCHEMA:
        raise BookIntakeError("unsupported books manifest version")
    if not isinstance(parsed.get("books"), list) or not parsed["books"]:
        raise BookIntakeError("at least one rights-reviewed book is necessary")
    return parsed, source


def _segments(text: str):
    """Lossless by construction: concatenated chunks MUST equal original text."""
    if len(text) < 20:
        raise BookIntakeError("chapter needs at least 20 characters for the trainer")
    start = 0
    while start < len(text):
        end = min(start + CHUNK_CHARS, len(text))
        if 0 < len(text) - end < 20:
            end = len(text)
        yield start, text[start:end]
        start = end


def _validate_book(root: Path, book: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    book_id = _id(book.get("id"), "book id")
    title = _text(book.get("title"), "book title", least=3, most=180)
    rights = _book_rights(book)
    chapters = book.get("chapters")
    if not isinstance(chapters, list) or not chapters:
        raise BookIntakeError("book requires an ordered non-empty chapter list")
    if len(chapters) > 4096:
        raise BookIntakeError("chapters need to be divided into separate book volumes")
    rows: list[dict[str, Any]] = []
    chapter_receipts: list[dict[str, object]] = []
    seen: set[str] = set()
    complete_text_hash = sha256()
    for chapter_no, chapter in enumerate(chapters):
        if not isinstance(chapter, dict):
            raise BookIntakeError("chapter review record must be an object")
        chapter_id = _id(chapter.get("id"), "chapter id")
        if chapter_id in seen:
            raise BookIntakeError("duplicate chapter identity")
        seen.add(chapter_id)
        filename = chapter.get("file")
        if (not isinstance(filename, str) or Path(filename).name != filename
                or filename in (".", "..") or not filename.endswith(".txt")):
            raise BookIntakeError("chapter filename must be a plain .txt basename")
        path = root / filename
        raw = _regular(path, max_bytes=MAX_SOURCE_BYTES)
        expected = chapter.get("sha256")
        if not isinstance(expected, str) or not HEX.fullmatch(expected) or _sha(raw) != expected:
            raise BookIntakeError("independently pinned chapter bytes differ")
        try:
            text = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise BookIntakeError("book chapters must be valid UTF-8") from exc
        if not text.strip():
            raise BookIntakeError("cannot train an empty chapter")
        complete_text_hash.update(text.encode("utf-8"))
        if chapter.get("family") not in FAMILIES:
            raise BookIntakeError("chapter needs an existing game curriculum family")
        if chapter.get("quality_approved") is not True:
            raise BookIntakeError("every chapter needs affirmative human quality review")
        reviewer = _text(chapter.get("quality_reviewer_id"), "human reviewer", least=3, most=128)
        note = _text(chapter.get("quality_review_note"), "chapter review note", least=24)
        if " Jeeves: " in text or "\nJeeves:" in text or "\nUser:" in text:
            raise BookIntakeError("source contains reserved training role delimiters")
        reconstructed: list[str] = []
        for segment_no, (start, span) in enumerate(_segments(text)):
            reconstructed.append(span)
            row_id = f"{book_id}.{chapter_id}.{segment_no:05d}"
            if len(row_id) > 128:
                raise BookIntakeError("book/chapter identifiers too long for corpus identity")
            prompt = (f"Study the reviewed {chapter['family']} source from {title}, "
                      f"chapter {chapter_id}, section {segment_no + 1}. "
                      "Explain how to apply its principles to an original game.")
            # This is the exact reviewed material, not invented Q/A or proof of mastery.
            # Preserving all characters also enables independent audit of ingestion.
            rows.append({
                "schema_version": INTAKE_SCHEMA,
                "id": row_id,
                "source_project_id": book_id,
                "family": chapter["family"],
                "prompt": prompt,
                "answer": span,
                "rights": rights,
                "quality_approved": True,
                "quality_reviewer_id": reviewer,
                "quality_review_note": note,
            })
        if "".join(reconstructed) != text:
            raise BookIntakeError("complete chapter byte coverage was lost")
        chapter_receipts.append({
            "chapter_id": chapter_id,
            "chapter_index": chapter_no,
            "source_sha256": expected,
            "normalized_text_sha256": _sha(text.encode("utf-8")),
            "characters_admitted": len(text),
            "characters_compiled": sum(map(len, reconstructed)),
            "chunks": len(reconstructed),
            "reviewer_id": reviewer,
            "human_review_note_sha256": _sha(note.encode("utf-8")),
        })
    return rows, {
        "book_id": book_id, "title": title,
        "rights_review_id": rights["review_id"],
        "rights_kind": rights["source_kind"],
        "chapters": chapter_receipts, "training_rows": len(rows),
        "source_text_sha256": complete_text_hash.hexdigest(),
    }


def compile_book_intake(manifest: Path, output_dir: Path, *,
                        operator_review_id: str) -> dict[str, object]:
    """Publish new, exclusively created shards and chained admission receipts.

    No optimizer runs here; actual model training is the existing pinned
    jeeves-production trainer, following independent train/heldout admission.
    """
    operator_review_id = _id(operator_review_id, "operator review")
    data, manifest_raw = _load_manifest(Path(manifest))
    root = Path(manifest).resolve().parent
    output_dir = Path(output_dir)
    if not output_dir.is_absolute() or output_dir.is_symlink() or not output_dir.is_dir():
        raise BookIntakeError("existing absolute non-symlink output directory required")
    books = data["books"]
    book_ids: set[str] = set()
    all_rows: list[dict[str, Any]] = []
    admissions: list[dict[str, Any]] = []
    row_ids: set[str] = set()
    for book in books:
        if not isinstance(book, dict):
            raise BookIntakeError("book metadata must be an object")
        rows, admission = _validate_book(root, book)
        if admission["book_id"] in book_ids:
            raise BookIntakeError("duplicate source book")
        book_ids.add(admission["book_id"])
        for row in rows:
            if row["id"] in row_ids:
                raise BookIntakeError("duplicate training record across books")
            row_ids.add(row["id"])
        all_rows.extend(rows)
        admissions.append(admission)
    # No truncation when a book is larger than one existing corpus intake.
    shards = [all_rows[i:i + MAX_SHARD_ROWS]
              for i in range(0, len(all_rows), MAX_SHARD_ROWS)]
    files: list[tuple[str, bytes]] = []
    heads: list[dict[str, object]] = []
    previous: str | None = None
    for i, shard in enumerate(shards):
        filename = f"jeeves-books-{operator_review_id}-{i:05d}.jsonl"
        payload = b"".join(_encode(row) + b"\n" for row in shard)
        if len(payload) > MAX_SOURCE_BYTES:
            raise BookIntakeError("shard exceeds the current training intake byte budget")
        head = {"index": i, "file": filename, "rows": len(shard),
                "sha256": _sha(payload), "previous_receipt": previous}
        previous = _sha(_encode(head))
        heads.append({**head, "receipt_sha256": previous})
        files.append((filename, payload))
    receipt = {
        "schema_version": "skeleton.jeeves.book_admission_receipt.v1",
        "manifest_sha256": _sha(manifest_raw),
        "operator_review_id": operator_review_id,
        "books": admissions,
        "shards": heads,
        "source_books": len(admissions),
        "training_examples": len(all_rows),
        "source_coverage_complete": True,
        "training_started": False,
        "production_weights_modified": False,
        "candidate_weights_created": False,
        "requires_independent_eval_and_checkpoint_pin": True,
    }
    receipt["digest"] = _sha(_encode(receipt))
    files.append((f"jeeves-books-{operator_review_id}-receipts.json", _encode(receipt)))
    for name, _ in files:
        if (output_dir / name).exists() or (output_dir / name).is_symlink():
            raise BookIntakeError("admission destination already exists; refusing overwrite")
    created: list[Path] = []
    try:
        for name, raw in files:
            target = output_dir / name
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            created.append(target)
            with os.fdopen(fd, "wb") as writer:
                writer.write(raw)
                writer.flush()
                os.fsync(writer.fileno())
    except BaseException:
        for file in created:
            file.unlink(missing_ok=True)
        raise
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--operator-review-id", required=True)
    args = parser.parse_args(argv)
    result = compile_book_intake(args.manifest, args.output_dir,
                                 operator_review_id=args.operator_review_id)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
