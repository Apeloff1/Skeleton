"""Private, rights-reviewed complete-book memory for Jeeves' LOCAL cortex.

The same admitted chapters used by the real candidate-weight optimizer can
augment inference immediately. This is local grounded retrieval, NOT substitute
weights, automatic legal clearance, or proof of learned model ability.
A private project-scoped FTS5 database retains source identity, a full source
digest, withdrawal history and per-query append-only evidence receipts.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sqlite3
from threading import RLock
from typing import Any, Mapping

SCHEMA = "skeleton.jeeves.reviewed_book_memory.v1"
MAX_ROWS = 100_000
MAX_QUERY = 1024
MAX_MATCHES = 8
MAX_RECEIPTS = 100_000
IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@+-]{0,127}$")
HEX = re.compile(r"^[a-f0-9]{64}$")
TOKEN = re.compile(r"[^\W_]+", re.UNICODE)


class BookMemoryError(ValueError):
    """Unverifiable corpus, invalid request, or corrupt indexed evidence."""


def _valid_id(value: object, label: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise BookMemoryError("invalid " + label)
    return value


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=True,
                          separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, RecursionError) as exc:
        raise BookMemoryError("noncanonical book evidence") from exc


def _hash(value: object) -> str:
    return sha256(_canonical(value)).hexdigest()


def _private_db(path: Path) -> Path:
    if not isinstance(path, Path) or not path.is_absolute() or path.is_symlink():
        raise BookMemoryError("book index requires a private absolute non-symlink path")
    if not path.parent.is_dir() or path.parent.is_symlink():
        raise BookMemoryError("book index needs an existing private directory")
    return path


class ReviewedBookMemory:
    """One project-bound local source memory with independently pinned admission."""

    def __init__(self, path: Path, *, project_id: str, admission_sha256: str,
                 expected_source_root_sha256: str) -> None:
        self.path = _private_db(path)
        self.project_id = _valid_id(project_id, "project")
        if not isinstance(admission_sha256, str) or not HEX.fullmatch(admission_sha256):
            raise BookMemoryError("independently pinned admission SHA-256 required")
        self.admission_sha256 = admission_sha256
        if (not isinstance(expected_source_root_sha256, str)
                or not HEX.fullmatch(expected_source_root_sha256)):
            raise BookMemoryError("independent indexed source-root SHA-256 required")
        self.expected_source_root_sha256 = expected_source_root_sha256
        if not path.is_file():
            raise BookMemoryError("admitted book index has not been built")
        self._lock = RLock()
        self._db = sqlite3.connect(str(path), timeout=10, isolation_level=None,
                                   check_same_thread=False)
        self._db.execute("PRAGMA busy_timeout=10000")
        self._db.execute("PRAGMA query_only=ON")
        try:
            self.verify()
            self._checked_data_version = self._db.execute(
                "PRAGMA data_version"
            ).fetchone()[0]
        except BaseException:
            self._db.close()
            raise

    @staticmethod
    def build(
        path: Path, *, project_id: str, admission_receipt: Path,
        admitted_dir: Path, expected_receipt_sha256: str,
    ) -> dict[str, Any]:
        """Create a new, immutable-intake memory. No provider or model training."""
        path = _private_db(path)
        project_id = _valid_id(project_id, "project")
        if path.exists() or path.is_symlink():
            raise BookMemoryError("cannot overwrite an existing indexed book memory")
        if not isinstance(expected_receipt_sha256, str) or not HEX.fullmatch(expected_receipt_sha256):
            raise BookMemoryError("operator must pin independent admission receipt bytes")
        # Import only at the operator build boundary, not at model boot.
        from skeleton.ai.training.book_weight_candidate import _all_rows, _receipt
        from skeleton.ai.training.book_learning_bridge import _regular, _sha

        admission_raw = _regular(Path(admission_receipt), max_bytes=1024 * 1024)
        if _sha(admission_raw) != expected_receipt_sha256:
            raise BookMemoryError("book admission differs from independently pinned bytes")
        receipt = _receipt(Path(admission_receipt))
        segments = _all_rows(receipt, Path(admitted_dir))
        if not 1 <= len(segments) <= MAX_ROWS:
            raise BookMemoryError("book memory outside indexed row limits")
        book_ids = {book["book_id"] for book in receipt["books"]}
        rows: list[tuple[str, str, str, str, str, str]] = []
        for key, item in sorted(segments.items()):
            if not isinstance(item, dict) or key != item.get("id"):
                raise BookMemoryError("indexed segment differs from reviewed row")
            book_id = item.get("source_project_id")
            if book_id not in book_ids:
                raise BookMemoryError("segment has no admitted source volume")
            text = item.get("answer")
            family = item.get("family")
            rights = item.get("rights")
            if (not isinstance(text, str) or not text.strip() or len(text) > 8192
                    or not isinstance(family, str) or not IDENTIFIER.fullmatch(family)
                    or not isinstance(rights, dict)
                    or rights.get("training_permitted") is not True
                    or rights.get("source_kind") not in
                    ("original_authoring", "licensed_training", "public_domain")):
                raise BookMemoryError("segment source or approved rights is invalid")
            rows.append((key, book_id, family, text,
                         sha256(text.encode("utf-8")).hexdigest(), _hash(rights)))
        source_root = _hash(rows)
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
        os.close(fd)
        db = None
        try:
            db = sqlite3.connect(str(path), isolation_level=None)
            db.executescript("""
                PRAGMA journal_mode=DELETE;
                CREATE TABLE metadata(
                    project_id TEXT NOT NULL, admission_sha TEXT NOT NULL,
                    source_root TEXT NOT NULL, source_count INTEGER NOT NULL
                );
                CREATE TABLE segment(
                    segment_id TEXT PRIMARY KEY, book_id TEXT NOT NULL,
                    family TEXT NOT NULL, text TEXT NOT NULL,
                    text_sha TEXT NOT NULL, rights_sha TEXT NOT NULL
                );
                CREATE VIRTUAL TABLE segment_search USING fts5(
                    segment_id UNINDEXED, text, tokenize='unicode61'
                );
                CREATE TABLE policy(
                    sequence INTEGER PRIMARY KEY,
                    book_id TEXT NOT NULL, reviewer_id TEXT NOT NULL,
                    reason TEXT NOT NULL, previous TEXT, digest TEXT NOT NULL UNIQUE
                );
                CREATE TABLE retrieval(
                    sequence INTEGER PRIMARY KEY, actor_id TEXT NOT NULL,
                    query_sha TEXT NOT NULL, filter_family TEXT,
                    result_sha TEXT NOT NULL, previous TEXT,
                    digest TEXT NOT NULL UNIQUE
                );
            """)
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT INTO metadata VALUES(?,?,?,?)", (
                project_id, expected_receipt_sha256, source_root, len(rows)))
            db.executemany("INSERT INTO segment VALUES(?,?,?,?,?,?)", rows)
            db.executemany("INSERT INTO segment_search(segment_id,text) VALUES (?,?)",
                           ((row[0], row[3]) for row in rows))
            db.execute("COMMIT")
            db.close()
            db = None
        except BaseException:
            if db is not None:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                db.close()
            path.unlink(missing_ok=True)
            raise
        return {
            "schema_version": SCHEMA, "project_id": project_id,
            "admission_receipt_sha256": expected_receipt_sha256,
            "source_root_sha256": source_root,
            "indexed_segments": len(rows), "model_weights_modified": False,
            "index_receipt_sha256": _hash([project_id, expected_receipt_sha256,
                                            source_root, len(rows)]),
        }

    def verify(self) -> dict[str, Any]:
        """Independently replay complete source, withdrawals and retrieval chains."""
        with self._lock:
            meta = self._db.execute(
                "SELECT project_id,admission_sha,source_root,source_count FROM metadata"
            ).fetchall()
            if (len(meta) != 1
                    or meta[0][:2] != (self.project_id, self.admission_sha256)
                    or meta[0][2] != self.expected_source_root_sha256):
                raise BookMemoryError("book memory project, admission or independently pinned source root changed")
            rows = self._db.execute(
                "SELECT segment_id,book_id,family,text,text_sha,rights_sha "
                "FROM segment ORDER BY segment_id"
            ).fetchall()
            if len(rows) != meta[0][3] or not 1 <= len(rows) <= MAX_ROWS:
                raise BookMemoryError("book memory lost a reviewed source segment")
            for row in rows:
                if sha256(row[3].encode("utf-8")).hexdigest() != row[4] or not HEX.fullmatch(row[5]):
                    raise BookMemoryError("book memory source text changed")
            if _hash(rows) != meta[0][2]:
                raise BookMemoryError("book memory source root does not match admission")
            indexed = self._db.execute(
                "SELECT segment_id,text FROM segment_search ORDER BY segment_id"
            ).fetchall()
            if indexed != [(item[0], item[3]) for item in rows]:
                raise BookMemoryError("full-book search index differs from source identity")
            for table, fields in (
                ("policy", "book_id,reviewer_id,reason"),
                ("retrieval", "actor_id,query_sha,filter_family,result_sha"),
            ):
                prev = None
                data = self._db.execute(
                    f"SELECT sequence,{fields},previous,digest FROM {table} ORDER BY sequence"
                ).fetchall()
                if len(data) > MAX_RECEIPTS:
                    raise BookMemoryError("book audit history needs archival")
                for n, record in enumerate(data):
                    if record[0] != n or record[-2] != prev:
                        raise BookMemoryError("book evidence history ancestry mismatch")
                    entry = dict(zip(fields.split(","), record[1:-2]))
                    payload = {"sequence": n, "previous": prev, **entry}
                    if _hash(payload) != record[-1]:
                        raise BookMemoryError("book evidence digest mismatch")
                    prev = record[-1]
            return {"source_root_sha256": meta[0][2], "segments": len(rows)}

    def _verify_external_changes(self) -> None:
        """Full replay on external writes; constant-time checks during local search.

        Our own connection only appends audited policies and retrieval events.
        SQLite data_version changes when another connection commits, so bulk
        book text is not rescanned on each local model inference.
        """
        current = self._db.execute("PRAGMA data_version").fetchone()[0]
        if current != self._checked_data_version:
            self.verify()
            self._checked_data_version = current

    def _event(self, table: str, fields: Mapping[str, object]) -> str:
        if table not in ("policy", "retrieval"):
            raise BookMemoryError("unsupported evidence event")
        columns = (("book_id","reviewer_id","reason") if table == "policy" else
                   ("actor_id","query_sha","filter_family","result_sha"))
        self._db.execute("PRAGMA query_only=OFF")
        self._db.execute("BEGIN IMMEDIATE")
        try:
            latest = self._db.execute(
                f"SELECT sequence,digest FROM {table} ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
            seq = latest[0] + 1 if latest else 0
            prior = latest[1] if latest else None
            if seq >= MAX_RECEIPTS:
                raise BookMemoryError("book evidence journal reached retention limit")
            body = {"sequence": seq, "previous": prior,
                    **{name: fields[name] for name in columns}}
            digest = _hash(body)
            names = "sequence," + ",".join(columns) + ",previous,digest"
            marks = ",".join("?" for _ in range(len(columns) + 3))
            self._db.execute(f"INSERT INTO {table}({names}) VALUES({marks})",
                             (seq, *(fields[name] for name in columns), prior, digest))
            self._db.execute("COMMIT")
            return digest
        except BaseException:
            if self._db.in_transaction:
                self._db.execute("ROLLBACK")
            raise
        finally:
            self._db.execute("PRAGMA query_only=ON")

    def revoke_book(self, book_id: str, *, reviewer_id: str,
                    reason: str) -> str:
        """Permanent exclusion from future inference, without false deletion claim."""
        _valid_id(book_id, "book")
        _valid_id(reviewer_id, "reviewer")
        if not isinstance(reason, str) or not 16 <= len(reason) <= 512:
            raise BookMemoryError("documented withdrawal reason required")
        with self._lock:
            self._verify_external_changes()
            if not self._db.execute(
                "SELECT 1 FROM segment WHERE book_id=? LIMIT 1", (book_id,)
            ).fetchone():
                raise BookMemoryError("unknown indexed source book")
            if self._db.execute(
                "SELECT 1 FROM policy WHERE book_id=? LIMIT 1", (book_id,)
            ).fetchone():
                raise BookMemoryError("book already withdrawn")
            return self._event("policy", {
                "book_id": book_id, "reviewer_id": reviewer_id, "reason": reason,
            })

    def search(self, query: str, *, actor_id: str, family: str | None = None,
               limit: int = 4, excerpt_chars: int = 480) -> dict[str, Any]:
        """Rank independently hashed, nonwithdrawn local paragraphs; log access."""
        _valid_id(actor_id, "requesting actor")
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= MAX_QUERY:
            raise BookMemoryError("book query must be bounded nonempty text")
        if family is not None:
            _valid_id(family, "family")
        if type(limit) is not int or not 1 <= limit <= MAX_MATCHES:
            raise BookMemoryError("bounded memory result count required")
        if type(excerpt_chars) is not int or not 160 <= excerpt_chars <= 960:
            raise BookMemoryError("bounded source excerpt length required")
        terms = list(dict.fromkeys(word.lower() for word in TOKEN.findall(query)
                                   if len(word) >= 2))[:16]
        if not terms:
            raise BookMemoryError("query has no searchable words")
        # Construct only quoted literal tokens: never accept FTS operators or
        # column syntax from user/model text.
        match = " OR ".join('"' + word.replace('"', '""') + '"' for word in terms)
        with self._lock:
            self._verify_external_changes()
            dbrows = self._db.execute(
                "SELECT s.segment_id,s.book_id,s.family,s.text,s.text_sha,s.rights_sha,"
                "bm25(segment_search) AS relevance "
                "FROM segment_search JOIN segment AS s "
                "ON s.segment_id=segment_search.segment_id "
                "WHERE segment_search MATCH ? AND (? IS NULL OR s.family=?) "
                "AND NOT EXISTS(SELECT 1 FROM policy p WHERE p.book_id=s.book_id) "
                "ORDER BY relevance ASC,s.segment_id ASC LIMIT ?",
                (match, family, family, limit),
            ).fetchall()
            for row in dbrows:
                if sha256(row[3].encode("utf-8")).hexdigest() != row[4]:
                    raise BookMemoryError("retrieved segment differs from source hash")
            citations = []
            for row in dbrows:
                source = row[3]
                # FTS may match deep into a full chapter: carry the relevant
                # reviewed span, not merely the first paragraph of a chunk.
                start_at = 0
                for term in sorted(terms, key=len, reverse=True):
                    hit = re.search(re.escape(term), source, re.IGNORECASE)
                    if hit:
                        start_at = max(0, hit.start() - excerpt_chars // 3)
                        break
                end_at = min(len(source), start_at + excerpt_chars)
                start_at = max(0, end_at - excerpt_chars)
                citations.append({
                    "segment_id": row[0], "book_id": row[1], "family": row[2],
                    "excerpt": source[start_at:end_at],
                    "excerpt_start": start_at, "excerpt_end": end_at,
                    "source_text_sha256": row[4],
                    "rights_sha256": row[5],
                    "truncated": start_at > 0 or end_at < len(source),
                    "score": round(float(row[6]), 8),
                })
            result_sha = _hash(citations)
            query_sha = sha256(query.encode("utf-8")).hexdigest()
            event = self._event("retrieval", {
                "actor_id": actor_id, "query_sha": query_sha,
                "filter_family": family, "result_sha": result_sha,
            })
            return {
                "schema_version": SCHEMA, "project_id": self.project_id,
                "admission_receipt_sha256": self.admission_sha256,
                "query_sha256": query_sha, "results": citations,
                "results_sha256": result_sha, "retrieval_receipt_sha256": event,
                "host_verified": True, "model_weights_modified": False,
            }

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> "ReviewedBookMemory":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def main(argv: list[str] | None = None) -> int:
    """Operator CLI for verified local Jeeves source admission and inspection."""
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("build", "search", "revoke", "verify"):
        run = sub.add_parser(command)
        run.add_argument("--index", required=True, type=Path)
        run.add_argument("--project-id", required=True)
        run.add_argument("--admission-sha256", required=True)
        if command != "build":
            run.add_argument("--source-root-sha256", required=True,
                             help="Separately retained source_root_sha256 from build receipt")
        if command == "build":
            run.add_argument("--admission-receipt", required=True, type=Path)
            run.add_argument("--admitted-dir", required=True, type=Path)
        elif command == "search":
            run.add_argument("--query", required=True)
            run.add_argument("--actor-id", required=True)
            run.add_argument("--family", default=None)
            run.add_argument("--limit", type=int, default=4)
        elif command == "revoke":
            run.add_argument("--book-id", required=True)
            run.add_argument("--reviewer-id", required=True)
            run.add_argument("--reason", required=True)
    args = parser.parse_args(argv)
    if args.command == "build":
        result = ReviewedBookMemory.build(
            args.index, project_id=args.project_id,
            admission_receipt=args.admission_receipt,
            admitted_dir=args.admitted_dir,
            expected_receipt_sha256=args.admission_sha256,
        )
    else:
        with ReviewedBookMemory(
            args.index, project_id=args.project_id,
            admission_sha256=args.admission_sha256,
            expected_source_root_sha256=args.source_root_sha256,
        ) as memory:
            if args.command == "verify":
                result = memory.verify()
            elif args.command == "search":
                result = memory.search(
                    args.query, actor_id=args.actor_id, family=args.family,
                    limit=args.limit,
                )
            else:
                result = {
                    "schema_version": SCHEMA, "project_id": args.project_id,
                    "withdrawn_book_id": args.book_id,
                    "withdrawal_receipt_sha256": memory.revoke_book(
                        args.book_id, reviewer_id=args.reviewer_id, reason=args.reason,
                    ),
                    "source_file_erased": False,
                }
    print(json.dumps(result, sort_keys=True))
    return 0


__all__ = ["ReviewedBookMemory", "BookMemoryError", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
