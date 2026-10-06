"""Durable deterministic code-search index for the repository machine.

The repository model remains the source of truth for inventory, ownership and
file hashes. This module adds a compact identifier index over that inventory:
one posting per identifier/document pair with occurrence counts and the best
line-level location. Definition locations outrank ordinary references.

The index deliberately does not persist source text. Search results identify
the exact repository path and line/column so callers can fetch current source
through the governed repository surface.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
from typing import Iterable, Mapping

from .code_index import CodeIndexError, extract_records, language_for_path
from .model import FileRecord, RepositoryModel, canonical_json

FORMAT = "skeleton-code-search-index"
VERSION = 1
MAX_INDEX_BYTES = 90 * 1024 * 1024
MAX_SOURCE_BYTES = 2_000_000
MAX_TERM_LENGTH = 128
MAX_POSTINGS = 2_000_000

_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]{1,127}")
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_PATH_SPLIT = re.compile(r"[/._:-]+")
_SAFE_TERM = re.compile(r"^[a-z_][a-z0-9_]{1,127}$")

_DEFAULT_EXCLUDED_ZONES = frozenset({"external-sources"})


class CodeSearchError(RuntimeError):
    """Raised when a code-search index cannot be built or trusted."""


def _repo_path(value: object) -> str:
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise CodeSearchError("index path must be non-empty canonical POSIX text")
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise CodeSearchError(f"unsafe repository path: {value!r}")
    if pure.as_posix() != value:
        raise CodeSearchError(f"non-canonical repository path: {value!r}")
    return value


def _query_terms(value: str) -> tuple[str, ...]:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("query must not be empty")
    expanded = _CAMEL.sub(" ", value)
    terms: set[str] = set()
    for token in _IDENTIFIER.findall(value):
        lowered = token.casefold()
        if len(lowered) <= MAX_TERM_LENGTH:
            terms.add(lowered)
    for token in _IDENTIFIER.findall(expanded):
        lowered = token.casefold()
        if len(lowered) <= MAX_TERM_LENGTH:
            terms.add(lowered)
    for part in _PATH_SPLIT.split(value.casefold()):
        if _SAFE_TERM.fullmatch(part or ""):
            terms.add(part)
    return tuple(sorted(terms))


def _path_terms(path: str) -> tuple[str, ...]:
    terms: set[str] = set()
    for part in _PATH_SPLIT.split(path.casefold()):
        if _SAFE_TERM.fullmatch(part or ""):
            terms.add(part)
    name = PurePosixPath(path).name.casefold()
    stem = PurePosixPath(path).stem.casefold()
    for value in (name, stem):
        if 2 <= len(value) <= MAX_TERM_LENGTH:
            terms.add(value)
    return tuple(sorted(terms))


def _definition_pattern(language: str, name: str) -> re.Pattern[str]:
    escaped = re.escape(name)
    if language == "python":
        prefix = r"(?:async\s+def|def|class)"
    elif language in {"javascript", "typescript"}:
        prefix = r"(?:(?:export\s+)?(?:async\s+)?function|(?:export\s+)?(?:class|interface|type|enum))"
    elif language == "go":
        prefix = r"(?:func|type)(?:\s+\([^)]*\))?"
    elif language == "rust":
        prefix = r"(?:pub(?:\([^)]*\))?\s+)?(?:fn|struct|enum|trait|type|mod)"
    elif language == "java":
        prefix = r"(?:(?:public|protected|private|abstract|final|static|sealed|non-sealed)\s+)*(?:class|interface|enum|record)"
    elif language == "kotlin":
        prefix = r"(?:(?:public|private|internal|protected|data|sealed|open|abstract)\s+)*(?:class|interface|object|fun|typealias)"
    elif language in {"c", "cpp"}:
        return re.compile(rf"\b{escaped}\s*\(")
    else:
        return re.compile(r"(?!x)x")
    return re.compile(rf"^\s*{prefix}\s+{escaped}\b")


def _safe_read(root: Path, record: FileRecord, max_source_bytes: int) -> bytes:
    path = root.joinpath(*PurePosixPath(_repo_path(record.path)).parts)
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise CodeSearchError(f"indexed source is unavailable: {record.path}") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise CodeSearchError(f"indexed source is not a regular file: {record.path}")
    if metadata.st_size != record.size:
        raise CodeSearchError(f"source size changed since repository model: {record.path}")
    if metadata.st_size > max_source_bytes:
        raise CodeSearchError(f"source exceeds code-search byte bound: {record.path}")

    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise CodeSearchError(f"indexed source cannot be resolved: {record.path}") from exc
    if not resolved.is_relative_to(root):
        raise CodeSearchError(f"indexed source escapes repository root: {record.path}")

    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise CodeSearchError(f"indexed source cannot be opened safely: {record.path}") from exc
    try:
        before = os.fstat(fd)
        with os.fdopen(fd, "rb", closefd=False) as handle:
            raw = handle.read(max_source_bytes + 1)
        after = os.fstat(fd)
        if (
            before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
        ):
            raise CodeSearchError(f"source changed during indexing: {record.path}")
        if len(raw) > max_source_bytes:
            raise CodeSearchError(f"source exceeds code-search byte bound: {record.path}")
    finally:
        os.close(fd)

    digest = hashlib.sha256(raw).hexdigest()
    if digest != record.sha256:
        raise CodeSearchError(f"source hash changed since repository model: {record.path}")
    return raw


@dataclass(frozen=True, slots=True)
class IndexedDocument:
    path: str
    language: str
    zone: str
    kind: str
    sha256: str

    def as_compact(self) -> list[object]:
        return [self.path, self.language, self.zone, self.kind, self.sha256]


@dataclass(frozen=True, slots=True)
class CodePosting:
    document: int
    line: int
    column: int
    kind: str
    count: int

    def as_compact(self) -> list[object]:
        return [self.document, self.line, self.column, self.kind, self.count]


@dataclass(frozen=True, slots=True)
class CodeSearchHit:
    path: str
    language: str
    zone: str
    kind: str
    score: int
    matched_terms: tuple[str, ...]
    line: int
    column: int
    match_kind: str
    occurrence_count: int
    reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "language": self.language,
            "zone": self.zone,
            "kind": self.kind,
            "score": self.score,
            "matched_terms": list(self.matched_terms),
            "line": self.line,
            "column": self.column,
            "match_kind": self.match_kind,
            "occurrence_count": self.occurrence_count,
            "reasons": list(self.reasons),
        }


class CodeSearchIndex:
    """Compact immutable identifier-to-document search index."""

    def __init__(
        self,
        *,
        repository: str,
        repository_fingerprint: str,
        documents: Iterable[IndexedDocument],
        postings: Mapping[str, Iterable[CodePosting]],
        skipped: Iterable[tuple[str, str]] = (),
    ) -> None:
        self.repository = str(repository)
        self.repository_fingerprint = str(repository_fingerprint)
        self.documents = tuple(documents)
        self.postings = {
            str(term): tuple(items)
            for term, items in sorted(postings.items())
        }
        self.skipped = tuple(sorted((str(path), str(reason)) for path, reason in skipped))
        self._path_postings: dict[str, set[int]] = {}
        self._prefix_terms: dict[str, tuple[str, ...]] = {}
        self._validate_runtime()
        self._build_auxiliary()

    def _validate_runtime(self) -> None:
        if not self.repository or not self.repository_fingerprint:
            raise CodeSearchError("index repository identity is missing")
        if len(self.repository_fingerprint) != 64:
            raise CodeSearchError("index repository fingerprint is invalid")
        paths = [item.path for item in self.documents]
        if paths != sorted(paths) or len(paths) != len(set(paths)):
            raise CodeSearchError("index documents must be sorted and unique")
        for item in self.documents:
            _repo_path(item.path)
        total = 0
        for term, items in self.postings.items():
            if _SAFE_TERM.fullmatch(term) is None:
                raise CodeSearchError(f"invalid index term: {term!r}")
            previous = -1
            for posting in items:
                if not 0 <= posting.document < len(self.documents):
                    raise CodeSearchError("posting references an unknown document")
                if posting.document < previous:
                    raise CodeSearchError("posting list is not document-sorted")
                previous = posting.document
                if posting.line < 1 or posting.column < 0 or posting.count < 1:
                    raise CodeSearchError("posting location/count is invalid")
                if posting.kind not in {"definition", "reference"}:
                    raise CodeSearchError("posting kind is invalid")
                total += 1
        if total > MAX_POSTINGS:
            raise CodeSearchError("code-search posting budget exceeded")
        for path, reason in self.skipped:
            _repo_path(path)
            if not reason:
                raise CodeSearchError("skipped index entry requires a reason")

    def _build_auxiliary(self) -> None:
        for document, item in enumerate(self.documents):
            for term in _path_terms(item.path):
                self._path_postings.setdefault(term, set()).add(document)
        prefixes: dict[str, list[str]] = {}
        for term in self.postings:
            prefixes.setdefault(term[:3], []).append(term)
        self._prefix_terms = {
            prefix: tuple(sorted(values))
            for prefix, values in prefixes.items()
        }

    @classmethod
    def build(
        cls,
        root: str | Path,
        model: RepositoryModel,
        *,
        max_source_bytes: int = MAX_SOURCE_BYTES,
        excluded_zones: Iterable[str] = _DEFAULT_EXCLUDED_ZONES,
    ) -> "CodeSearchIndex":
        if model.truncated:
            raise CodeSearchError("refusing to build code search from a truncated repository model")
        if isinstance(max_source_bytes, bool) or not isinstance(max_source_bytes, int) or max_source_bytes < 1:
            raise ValueError("max_source_bytes must be a positive integer")

        root_path = Path(root).resolve()
        excluded = {str(zone) for zone in excluded_zones}
        candidates = [
            record for record in model.files
            if record.kind in {"source", "test"}
            and record.zone not in excluded
            and language_for_path(record.path) is not None
        ]
        candidates.sort(key=lambda item: item.path)

        documents: list[IndexedDocument] = []
        postings: dict[str, list[CodePosting]] = {}
        skipped: list[tuple[str, str]] = []
        posting_count = 0

        for record in candidates:
            if record.size > max_source_bytes:
                skipped.append((record.path, "source exceeds configured byte bound"))
                continue
            try:
                raw = _safe_read(root_path, record, max_source_bytes)
                content = raw.decode("utf-8")
            except UnicodeDecodeError:
                skipped.append((record.path, "source is not UTF-8 text"))
                continue
            except CodeSearchError:
                raise

            language = language_for_path(record.path)
            if language is None:
                continue
            try:
                symbols, _references = extract_records(record.path, content)
            except CodeIndexError as exc:
                skipped.append((record.path, f"static parser rejected source: {exc}"))
                continue

            document_id = len(documents)
            documents.append(IndexedDocument(
                path=record.path,
                language=language,
                zone=record.zone,
                kind=record.kind,
                sha256=record.sha256,
            ))
            symbol_names = {symbol.name.casefold() for symbol in symbols}
            definition_patterns = {
                name: _definition_pattern(language, name)
                for name in symbol_names
            }

            # term -> [count, first_line, first_column, definition_line, definition_column]
            local: dict[str, list[int]] = {}
            for line_number, line in enumerate(content.splitlines(), start=1):
                seen_on_line: set[str] = set()
                for match in _IDENTIFIER.finditer(line):
                    term = match.group(0).casefold()
                    if term in seen_on_line or len(term) > MAX_TERM_LENGTH:
                        continue
                    seen_on_line.add(term)
                    state = local.get(term)
                    if state is None:
                        state = [0, line_number, match.start(), 0, 0]
                        local[term] = state
                    state[0] += 1
                    if (
                        term in symbol_names
                        and state[3] == 0
                        and definition_patterns[term].search(line)
                    ):
                        state[3] = line_number
                        state[4] = match.start()

            for term in sorted(local):
                count, first_line, first_column, definition_line, definition_column = local[term]
                is_definition = definition_line > 0
                posting = CodePosting(
                    document=document_id,
                    line=definition_line if is_definition else first_line,
                    column=definition_column if is_definition else first_column,
                    kind="definition" if is_definition else "reference",
                    count=count,
                )
                postings.setdefault(term, []).append(posting)
                posting_count += 1
                if posting_count > MAX_POSTINGS:
                    raise CodeSearchError(
                        f"code-search posting budget exceeded ({MAX_POSTINGS})"
                    )

        return cls(
            repository=model.repository,
            repository_fingerprint=model.fingerprint,
            documents=documents,
            postings=postings,
            skipped=skipped,
        )

    @property
    def posting_count(self) -> int:
        return sum(len(items) for items in self.postings.values())

    def summary(self) -> dict[str, object]:
        languages: dict[str, int] = {}
        for item in self.documents:
            languages[item.language] = languages.get(item.language, 0) + 1
        return {
            "format": FORMAT,
            "version": VERSION,
            "repository": self.repository,
            "repository_fingerprint": self.repository_fingerprint,
            "documents": len(self.documents),
            "terms": len(self.postings),
            "postings": self.posting_count,
            "skipped": len(self.skipped),
            "languages": dict(sorted(languages.items())),
        }

    def search(
        self,
        query: str,
        *,
        languages: Iterable[str] = (),
        zones: Iterable[str] = (),
        kinds: Iterable[str] = (),
        limit: int = 40,
    ) -> tuple[CodeSearchHit, ...]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
            raise ValueError("limit must be in [1,500]")
        terms = _query_terms(query)
        if not terms:
            return ()

        language_set = {str(value).casefold() for value in languages}
        zone_set = {str(value).casefold() for value in zones}
        kind_set = {str(value).casefold() for value in kinds}

        by_document: dict[int, dict[str, CodePosting]] = {}
        path_matches: dict[int, set[str]] = {}
        for term in terms:
            for posting in self.postings.get(term, ()):
                by_document.setdefault(posting.document, {})[term] = posting
            for document in self._path_postings.get(term, ()):
                path_matches.setdefault(document, set()).add(term)

        if not by_document and not path_matches:
            for term in sorted(terms, key=lambda value: (len(value), value)):
                prefix = term[:3]
                for indexed_term in self._prefix_terms.get(prefix, ()):
                    if indexed_term.startswith(term) or term.startswith(indexed_term):
                        for posting in self.postings[indexed_term]:
                            by_document.setdefault(posting.document, {})[indexed_term] = posting
                if by_document:
                    break

        candidates = set(by_document) | set(path_matches)
        hits: list[CodeSearchHit] = []
        query_lower = query.casefold().strip()
        query_term_set = set(terms)

        for document_id in candidates:
            document = self.documents[document_id]
            if language_set and document.language.casefold() not in language_set:
                continue
            if zone_set and document.zone.casefold() not in zone_set:
                continue
            if kind_set and document.kind.casefold() not in kind_set:
                continue

            term_postings = by_document.get(document_id, {})
            matched = set(term_postings)
            matched.update(path_matches.get(document_id, ()))
            score = 0
            reasons: list[str] = []
            occurrence_count = 0
            best: CodePosting | None = None

            for term, posting in sorted(term_postings.items()):
                document_frequency = len(self.postings.get(term, ()))
                rarity = max(0, 24 - max(0, document_frequency.bit_length() - 1) * 3)
                score += 18 + rarity + min(posting.count, 12)
                occurrence_count += posting.count
                if posting.kind == "definition":
                    score += 45
                    reasons.append(f"definition:{term}")
                if (
                    best is None
                    or (posting.kind == "definition" and best.kind != "definition")
                    or (
                        posting.kind == best.kind
                        and (posting.line, posting.column) < (best.line, best.column)
                    )
                ):
                    best = posting

            path_lower = document.path.casefold()
            basename = PurePosixPath(document.path).name.casefold()
            stem = PurePosixPath(document.path).stem.casefold()
            if query_lower in path_lower:
                score += 35
                reasons.append("query substring appears in path")
            if query_lower in {basename, stem}:
                score += 70
                reasons.append("query exactly matches file basename")
            if path_matches.get(document_id):
                score += 8 * len(path_matches[document_id])
                reasons.append("query terms match path")
            if query_term_set and query_term_set.issubset(matched):
                score += 25
                reasons.append("all query terms matched")
            if document.kind == "source":
                score += 3

            if best is None:
                best = CodePosting(document_id, 1, 0, "reference", 1)

            hits.append(CodeSearchHit(
                path=document.path,
                language=document.language,
                zone=document.zone,
                kind=document.kind,
                score=score,
                matched_terms=tuple(sorted(matched)),
                line=best.line,
                column=best.column,
                match_kind=best.kind,
                occurrence_count=occurrence_count,
                reasons=tuple(reasons),
            ))

        hits.sort(key=lambda item: (-item.score, item.path, item.line, item.column))
        return tuple(hits[:limit])


def _state(index: CodeSearchIndex) -> dict[str, object]:
    return {
        "repository": index.repository,
        "repository_fingerprint": index.repository_fingerprint,
        "documents": [item.as_compact() for item in index.documents],
        "postings": {
            term: [posting.as_compact() for posting in items]
            for term, items in index.postings.items()
        },
        "skipped": [list(item) for item in index.skipped],
    }


def _checksum(state: object) -> str:
    return hashlib.sha256(canonical_json(state).encode("utf-8")).hexdigest()


def index_envelope(index: CodeSearchIndex) -> dict[str, object]:
    state = _state(index)
    return {
        "format": FORMAT,
        "version": VERSION,
        "checksum": _checksum(state),
        "state": state,
    }


def save_code_search_index(index: CodeSearchIndex, path: str | Path) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    rendered = canonical_json(index_envelope(index)) + "\n"
    encoded = rendered.encode("utf-8")
    if len(encoded) > MAX_INDEX_BYTES:
        raise CodeSearchError("code-search index exceeds byte budget")

    fd, temp_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
        text=False,
    )
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, destination)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise


def load_code_search_index(
    path: str | Path,
    *,
    expected_fingerprint: str | None = None,
) -> CodeSearchIndex:
    source = Path(path)
    try:
        metadata = source.lstat()
    except OSError as exc:
        raise CodeSearchError("code-search index is unavailable") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise CodeSearchError("code-search index must be a regular non-symlink file")
    if metadata.st_size <= 0 or metadata.st_size > MAX_INDEX_BYTES:
        raise CodeSearchError("code-search index exceeds byte budget")

    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(source, flags)
    except OSError as exc:
        raise CodeSearchError("code-search index cannot be opened safely") from exc
    try:
        before = os.fstat(fd)
        with os.fdopen(fd, "rb", closefd=False) as handle:
            raw = handle.read(MAX_INDEX_BYTES + 1)
        after = os.fstat(fd)
        if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
            raise CodeSearchError("code-search index changed during read")
        if len(raw) > MAX_INDEX_BYTES:
            raise CodeSearchError("code-search index exceeds byte budget")
    finally:
        os.close(fd)

    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CodeSearchError("code-search index is invalid JSON") from exc
    return validate_code_search_index(payload, expected_fingerprint=expected_fingerprint)


def validate_code_search_index(
    payload: Mapping[str, object],
    *,
    expected_fingerprint: str | None = None,
) -> CodeSearchIndex:
    if payload.get("format") != FORMAT or payload.get("version") != VERSION:
        raise CodeSearchError("unsupported code-search index format")
    state = payload.get("state")
    if not isinstance(state, dict):
        raise CodeSearchError("code-search index state missing")
    if payload.get("checksum") != _checksum(state):
        raise CodeSearchError("code-search index checksum mismatch")

    repository = state.get("repository")
    fingerprint = state.get("repository_fingerprint")
    if not isinstance(repository, str) or not repository:
        raise CodeSearchError("code-search repository identity missing")
    if not isinstance(fingerprint, str) or len(fingerprint) != 64:
        raise CodeSearchError("code-search repository fingerprint invalid")
    if expected_fingerprint is not None and fingerprint != expected_fingerprint:
        raise CodeSearchError("code-search index does not match repository fingerprint")

    raw_documents = state.get("documents")
    raw_postings = state.get("postings")
    raw_skipped = state.get("skipped", [])
    if not isinstance(raw_documents, list) or not isinstance(raw_postings, dict):
        raise CodeSearchError("code-search index data missing")
    if not isinstance(raw_skipped, list):
        raise CodeSearchError("code-search skipped inventory invalid")

    documents: list[IndexedDocument] = []
    for raw_document in raw_documents:
        if not isinstance(raw_document, list) or len(raw_document) != 5:
            raise CodeSearchError("invalid code-search document record")
        path, language, zone, kind, sha256 = raw_document
        if not all(isinstance(value, str) for value in raw_document):
            raise CodeSearchError("invalid code-search document field")
        if not re.fullmatch(r"[0-9a-f]{64}", sha256):
            raise CodeSearchError("invalid code-search document digest")
        documents.append(IndexedDocument(_repo_path(path), language, zone, kind, sha256))

    postings: dict[str, list[CodePosting]] = {}
    for term, raw_items in raw_postings.items():
        if not isinstance(term, str) or _SAFE_TERM.fullmatch(term) is None:
            raise CodeSearchError("invalid code-search term")
        if not isinstance(raw_items, list):
            raise CodeSearchError("invalid code-search posting list")
        items: list[CodePosting] = []
        for raw_item in raw_items:
            if not isinstance(raw_item, list) or len(raw_item) != 5:
                raise CodeSearchError("invalid code-search posting")
            document, line, column, kind, count = raw_item
            if (
                isinstance(document, bool) or not isinstance(document, int)
                or isinstance(line, bool) or not isinstance(line, int)
                or isinstance(column, bool) or not isinstance(column, int)
                or not isinstance(kind, str)
                or isinstance(count, bool) or not isinstance(count, int)
            ):
                raise CodeSearchError("invalid code-search posting field")
            items.append(CodePosting(document, line, column, kind, count))
        postings[term] = items

    skipped: list[tuple[str, str]] = []
    for raw_item in raw_skipped:
        if (
            not isinstance(raw_item, list)
            or len(raw_item) != 2
            or not all(isinstance(value, str) for value in raw_item)
        ):
            raise CodeSearchError("invalid skipped code-search record")
        skipped.append((_repo_path(raw_item[0]), raw_item[1]))

    return CodeSearchIndex(
        repository=repository,
        repository_fingerprint=fingerprint,
        documents=documents,
        postings=postings,
        skipped=skipped,
    )


__all__ = [
    "CodeSearchError",
    "CodeSearchHit",
    "CodeSearchIndex",
    "IndexedDocument",
    "MAX_INDEX_BYTES",
    "MAX_POSTINGS",
    "MAX_SOURCE_BYTES",
    "index_envelope",
    "load_code_search_index",
    "save_code_search_index",
    "validate_code_search_index",
]
