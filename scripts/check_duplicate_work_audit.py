#!/usr/bin/env python3
"""Fail-closed duplicate/superseded PR-cluster inventory (#969 S009).

Issue #969 Seed 05 (``reserve-S009-duplicate-work-audit``) classifies an
explicit fixture table of pull requests. Each row is ``{number, title, head,
files, state}``. Clusters form only from explicit identity:

* the same ``head`` branch, or
* the same normalized title **and** the same full file-path set, or
* a title that names another row (``supersedes #N``, ``replaces #N``,
  ``duplicate of #N``)

Basename overlap, partial path overlap, and title-only similarity are not
clusters. This inventory does not own Seed 20
(``reserve-S097-legacy-duplicate-inventory``), which classifies duplicate
*contracts* in the tree, not pull-request clusters.

Classes:

* unique — no explicit cluster mate, or the surviving member of a cluster
* duplicate — extra *open* PR in a cluster of concurrent opens
* superseded — replaced by an explicit title ref, a later survivor, or a
  landed merge in the same cluster
* unknown — invalid row or unresolvable title ref (always a gate failure)

Unknown fails closed. The checker never closes, comments on, or otherwise
mutates pull requests.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence


TASK_KEY = "reserve-S009-duplicate-work-audit"
CONFLICT_DOMAIN = "repo.readonly.duplicate_work"
INVENTORY_VERSION = 1
SCHEMA_VERSION = 1
EVIDENCE_KIND = "structural"
AUTO_CLOSE = False
MUTATION_ACTIONS: tuple[str, ...] = ()
_FINDING_PREFIX = "duplicate-work"

CLASS_UNIQUE = "unique"
CLASS_DUPLICATE = "duplicate"
CLASS_SUPERSEDED = "superseded"
CLASS_UNKNOWN = "unknown"
CLASSES: tuple[str, ...] = (
    CLASS_UNIQUE,
    CLASS_DUPLICATE,
    CLASS_SUPERSEDED,
    CLASS_UNKNOWN,
)
CLASS_SET = frozenset(CLASSES)

DOCUMENT_FIELDS = frozenset({"schema_version", "prs"})
PR_FIELDS = frozenset({"number", "title", "head", "files", "state"})
KNOWN_STATES = frozenset({"open", "closed", "merged"})

TITLE_REF_RE = re.compile(
    r"\b(?P<kind>superse(?:de[sd]?|ding)|replaces?|duplicate of)\s+#(?P<number>\d+)\b",
    re.IGNORECASE,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "duplicate_work_audit.v1.json"


class DuplicateWorkAuditError(RuntimeError):
    """Raised when the PR-cluster inventory cannot classify fail-closed."""


@dataclass(frozen=True, slots=True)
class ParsedPR:
    """One validated fixture row, or an unknown parse failure."""

    index: int
    number: object
    title: object
    head: object
    files: object
    state: object
    norm_title: str = ""
    file_set: frozenset[str] = frozenset()
    refs: tuple[tuple[str, int], ...] = ()
    parse_error: str = ""

    @property
    def ok(self) -> bool:
        return not self.parse_error and isinstance(self.number, int)


@dataclass(frozen=True, slots=True)
class ClassifiedPR:
    """One classified fixture row."""

    index: int
    number: object
    classification: str
    cluster_id: str
    state: object
    title: object
    head: object
    files: tuple[object, ...]
    evidence: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "number": self.number,
            "class": self.classification,
            "cluster_id": self.cluster_id,
            "state": self.state,
            "title": self.title,
            "head": self.head,
            "files": list(self.files),
            "evidence": list(self.evidence),
        }


def _error(code: str, message: str) -> str:
    return f"{_FINDING_PREFIX} {code}: {message}"


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _norm_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    return text.casefold() if text else None


def _ref_kind(raw: str) -> str:
    text = raw.casefold()
    if text.startswith("dup"):
        return "duplicate"
    if text.startswith("rep"):
        return "replace"
    return "supersede"


def parse_title_refs(title: str) -> tuple[tuple[str, int], ...]:
    """Return explicit title references. Title-only similarity is ignored."""

    refs: list[tuple[str, int]] = []
    seen: set[tuple[str, int]] = set()
    for match in TITLE_REF_RE.finditer(title):
        item = (_ref_kind(match.group("kind")), int(match.group("number")))
        if item not in seen:
            seen.add(item)
            refs.append(item)
    return tuple(refs)


def _validate_files(files: object) -> tuple[frozenset[str], str]:
    if not isinstance(files, list):
        return frozenset(), "files must be a list of posix paths"
    paths: list[str] = []
    seen: set[str] = set()
    for item in files:
        if not isinstance(item, str) or not item.strip():
            return frozenset(), "files entries must be non-empty strings"
        path = item.strip()
        if "\\" in path or path.startswith("/") or path.startswith("./"):
            return frozenset(), f"file path is not a normalized relative posix path: {path!r}"
        parts = path.split("/")
        if any(part in {"", ".", ".."} for part in parts):
            return frozenset(), f"file path is not a normalized relative posix path: {path!r}"
        if path in seen:
            return frozenset(), f"files contains a duplicate path: {path}"
        seen.add(path)
        paths.append(path)
    return frozenset(paths), ""


def parse_pr(raw: object, *, index: int) -> ParsedPR:
    """Parse one fixture row. Malformed rows become unknown, not guessed."""

    if not isinstance(raw, Mapping):
        return ParsedPR(
            index=index,
            number=index,
            title=None,
            head=None,
            files=(),
            state=None,
            parse_error="pr row must be an object",
        )
    unknown = set(raw) - PR_FIELDS
    if unknown:
        return ParsedPR(
            index=index,
            number=raw.get("number", index),
            title=raw.get("title"),
            head=raw.get("head"),
            files=raw.get("files", ()),
            state=raw.get("state"),
            parse_error="unknown fields: " + ", ".join(sorted(str(item) for item in unknown)),
        )
    missing = PR_FIELDS - set(raw)
    if missing:
        return ParsedPR(
            index=index,
            number=raw.get("number", index),
            title=raw.get("title"),
            head=raw.get("head"),
            files=raw.get("files", ()),
            state=raw.get("state"),
            parse_error="missing fields: " + ", ".join(sorted(missing)),
        )

    number = raw.get("number")
    if not _is_int(number) or int(number) < 1:
        return ParsedPR(
            index=index,
            number=number,
            title=raw.get("title"),
            head=raw.get("head"),
            files=raw.get("files", ()),
            state=raw.get("state"),
            parse_error="number must be an integer >= 1",
        )

    title = raw.get("title")
    norm_title = _norm_text(title)
    if norm_title is None:
        return ParsedPR(
            index=index,
            number=number,
            title=title,
            head=raw.get("head"),
            files=raw.get("files", ()),
            state=raw.get("state"),
            parse_error="title must be a non-empty string",
        )

    head = raw.get("head")
    norm_head = _norm_text(head) if isinstance(head, str) else None
    if not isinstance(head, str) or not head.strip() or norm_head is None:
        return ParsedPR(
            index=index,
            number=number,
            title=title,
            head=head,
            files=raw.get("files", ()),
            state=raw.get("state"),
            parse_error="head must be a non-empty string",
        )

    file_set, file_error = _validate_files(raw.get("files"))
    if file_error:
        return ParsedPR(
            index=index,
            number=number,
            title=title,
            head=head,
            files=raw.get("files", ()),
            state=raw.get("state"),
            parse_error=file_error,
        )

    state_raw = raw.get("state")
    state = _norm_text(state_raw) if isinstance(state_raw, str) else None
    if state not in KNOWN_STATES:
        return ParsedPR(
            index=index,
            number=number,
            title=title,
            head=head,
            files=raw.get("files", ()),
            state=state_raw,
            parse_error="state must be open, closed, or merged",
        )

    refs = parse_title_refs(str(title))
    for kind, target in refs:
        if target == number:
            return ParsedPR(
                index=index,
                number=number,
                title=title,
                head=head,
                files=raw.get("files", ()),
                state=state,
                parse_error=f"title reference {kind} #{target} points at itself",
            )

    return ParsedPR(
        index=index,
        number=int(number),
        title=str(title),
        head=head.strip(),
        files=tuple(sorted(file_set)),
        state=state,
        norm_title=norm_title,
        file_set=file_set,
        refs=refs,
    )


class _UnionFind:
    def __init__(self, items: Iterable[int]) -> None:
        self.parent = {item: item for item in items}

    def find(self, item: int) -> int:
        parent = self.parent[item]
        if parent != item:
            parent = self.find(parent)
            self.parent[item] = parent
        return parent

    def union(self, left: int, right: int) -> None:
        root_left = self.find(left)
        root_right = self.find(right)
        if root_left != root_right:
            self.parent[root_right] = root_left


def _cluster_id(numbers: Sequence[int]) -> str:
    return f"cluster:{min(numbers)}"


def _same_head_groups(members: Sequence[ParsedPR]) -> list[str]:
    grouped: dict[str, list[int]] = {}
    for item in members:
        grouped.setdefault(str(item.head).casefold(), []).append(int(item.number))
    evidence: list[str] = []
    for head, numbers in grouped.items():
        if len(numbers) > 1:
            joined = ",".join(str(item) for item in sorted(numbers))
            evidence.append(f"same_head:{joined}")
    return evidence


def _same_title_files_groups(members: Sequence[ParsedPR]) -> list[str]:
    grouped: dict[tuple[str, frozenset[str]], list[int]] = {}
    for item in members:
        grouped.setdefault((item.norm_title, item.file_set), []).append(int(item.number))
    evidence: list[str] = []
    for _, numbers in grouped.items():
        if len(numbers) > 1:
            joined = ",".join(str(item) for item in sorted(numbers))
            evidence.append(f"same_title_and_files:{joined}")
    return evidence


def _title_ref_evidence(members: Sequence[ParsedPR]) -> list[str]:
    evidence: list[str] = []
    for item in members:
        for kind, target in item.refs:
            evidence.append(f"title_ref:{kind}:{item.number}->{target}")
    return evidence


def _classify_cluster(members: Sequence[ParsedPR]) -> dict[int, tuple[str, tuple[str, ...]]]:
    """Assign exclusive classes inside one explicit cluster."""

    ordered = sorted(members, key=lambda item: int(item.number))
    numbers = [int(item.number) for item in ordered]
    evidence = (
        _same_head_groups(ordered)
        + _same_title_files_groups(ordered)
        + _title_ref_evidence(ordered)
    )
    if len(ordered) == 1:
        return {
            numbers[0]: (CLASS_UNIQUE, ("unique_identity",)),
        }

    assigned: dict[int, str] = {}
    for item in ordered:
        for kind, target in item.refs:
            if kind in {"supersede", "replace"}:
                assigned[target] = CLASS_SUPERSEDED
            elif kind == "duplicate":
                assigned[int(item.number)] = CLASS_DUPLICATE

    remaining = [item for item in ordered if int(item.number) not in assigned]
    merged = [item for item in remaining if item.state == "merged"]
    opened = [item for item in remaining if item.state == "open"]
    closed = [item for item in remaining if item.state == "closed"]

    if merged:
        survivor = max(merged, key=lambda item: int(item.number))
        assigned[int(survivor.number)] = CLASS_UNIQUE
        for item in remaining:
            if item is survivor:
                continue
            assigned[int(item.number)] = CLASS_SUPERSEDED
    elif opened:
        survivor = min(opened, key=lambda item: int(item.number))
        assigned[int(survivor.number)] = CLASS_UNIQUE
        for item in opened:
            if item is survivor:
                continue
            assigned[int(item.number)] = CLASS_DUPLICATE
        for item in closed:
            assigned[int(item.number)] = CLASS_SUPERSEDED
    else:
        survivor = max(remaining, key=lambda item: int(item.number))
        assigned[int(survivor.number)] = CLASS_UNIQUE
        for item in remaining:
            if item is survivor:
                continue
            assigned[int(item.number)] = CLASS_SUPERSEDED

    result: dict[int, tuple[str, tuple[str, ...]]] = {}
    for item in ordered:
        number = int(item.number)
        result[number] = (assigned[number], tuple(evidence))
    return result


def classify_prs(prs: Sequence[object]) -> tuple[list[ClassifiedPR], list[str]]:
    """Classify a fixture table. Unknown rows are violations."""

    parsed = [parse_pr(item, index=index) for index, item in enumerate(prs)]
    errors: list[str] = []
    rows: list[ClassifiedPR] = []

    numbers: dict[int, ParsedPR] = {}
    valid: list[ParsedPR] = []
    for item in parsed:
        if not item.ok:
            errors.append(
                _error(
                    "unknown unclassified",
                    f"prs[{item.index}] number={item.number!r} {item.parse_error}",
                )
            )
            files = item.files if isinstance(item.files, (list, tuple)) else ()
            rows.append(
                ClassifiedPR(
                    index=item.index,
                    number=item.number,
                    classification=CLASS_UNKNOWN,
                    cluster_id="cluster:unknown",
                    state=item.state,
                    title=item.title,
                    head=item.head,
                    files=tuple(files) if isinstance(files, (list, tuple)) else (),
                    evidence=(item.parse_error or "unclassified",),
                )
            )
            continue
        number = int(item.number)
        if number in numbers:
            errors.append(
                _error(
                    "unknown unclassified",
                    f"prs[{item.index}] number={number} repeats prs[{numbers[number].index}]",
                )
            )
            rows.append(
                ClassifiedPR(
                    index=item.index,
                    number=number,
                    classification=CLASS_UNKNOWN,
                    cluster_id="cluster:unknown",
                    state=item.state,
                    title=item.title,
                    head=item.head,
                    files=tuple(item.files) if isinstance(item.files, tuple) else (),
                    evidence=(f"duplicate fixture number {number}",),
                )
            )
            continue
        numbers[number] = item
        valid.append(item)

    unresolved: set[int] = set()
    for item in valid:
        for kind, target in item.refs:
            if target not in numbers:
                unresolved.add(int(item.number))
                errors.append(
                    _error(
                        "unknown unclassified",
                        f"prs[{item.index}] number={item.number} {kind} #{target} is not in the fixture",
                    )
                )

    clusterable = [item for item in valid if int(item.number) not in unresolved]
    forest = _UnionFind(int(item.number) for item in clusterable)

    by_head: dict[str, list[int]] = {}
    by_title_files: dict[tuple[str, frozenset[str]], list[int]] = {}
    for item in clusterable:
        number = int(item.number)
        by_head.setdefault(str(item.head).casefold(), []).append(number)
        by_title_files.setdefault((item.norm_title, item.file_set), []).append(number)
        for _, target in item.refs:
            if target in forest.parent:
                forest.union(number, target)

    for group in by_head.values():
        first = group[0]
        for other in group[1:]:
            forest.union(first, other)
    for group in by_title_files.values():
        first = group[0]
        for other in group[1:]:
            forest.union(first, other)

    components: dict[int, list[ParsedPR]] = {}
    for item in clusterable:
        number = int(item.number)
        components.setdefault(forest.find(number), []).append(item)

    classified: dict[int, ClassifiedPR] = {}
    for members in components.values():
        cluster = _cluster_id([int(item.number) for item in members])
        assignments = _classify_cluster(members)
        for item in members:
            number = int(item.number)
            klass, evidence = assignments[number]
            classified[number] = ClassifiedPR(
                index=item.index,
                number=number,
                classification=klass,
                cluster_id=cluster,
                state=item.state,
                title=item.title,
                head=item.head,
                files=tuple(item.files) if isinstance(item.files, tuple) else (),
                evidence=evidence,
            )

    for item in valid:
        number = int(item.number)
        if number in unresolved:
            rows.append(
                ClassifiedPR(
                    index=item.index,
                    number=number,
                    classification=CLASS_UNKNOWN,
                    cluster_id="cluster:unknown",
                    state=item.state,
                    title=item.title,
                    head=item.head,
                    files=tuple(item.files) if isinstance(item.files, tuple) else (),
                    evidence=("unresolvable title reference",),
                )
            )
            continue
        rows.append(classified[number])

    rows.sort(key=lambda item: (item.index, str(item.number)))
    return rows, errors


def classify_document(document: object) -> tuple[list[ClassifiedPR], list[str]]:
    """Classify a versioned fixture document. Unknown fails closed."""

    if not isinstance(document, Mapping):
        return [], [_error("unknown root_type", "document must be an object")]

    errors: list[str] = []
    unknown = set(document) - DOCUMENT_FIELDS
    if unknown:
        errors.append(
            _error(
                "unknown field",
                "document has unknown fields: " + ", ".join(sorted(str(item) for item in unknown)),
            )
        )
    version = document.get("schema_version")
    if version != SCHEMA_VERSION:
        errors.append(
            _error("unknown schema_version", f"must be exactly {SCHEMA_VERSION}")
        )
    prs = document.get("prs")
    if not isinstance(prs, list):
        errors.append(_error("unknown prs_type", "prs must be a list"))
        return [], errors
    if not prs:
        errors.append(_error("unknown coverage", "fixture table must classify at least one PR"))
        return [], errors

    rows, row_errors = classify_prs(prs)
    errors.extend(row_errors)
    return rows, errors


def load_document(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DuplicateWorkAuditError(
            _error("unreadable missing_doc", f"{path} is missing")
        ) from exc
    except OSError as exc:
        raise DuplicateWorkAuditError(
            _error("unreadable io_error", f"cannot read {path}: {type(exc).__name__}")
        ) from exc
    except json.JSONDecodeError as exc:
        raise DuplicateWorkAuditError(
            _error("unreadable json", f"invalid JSON in {path} at line {exc.lineno}")
        ) from exc


def count_class(rows: Iterable[ClassifiedPR], classification: str) -> int:
    return sum(1 for row in rows if row.classification == classification)


def report_from_rows(rows: Sequence[ClassifiedPR]) -> dict[str, object]:
    if not rows:
        raise DuplicateWorkAuditError(_error("unknown coverage", "zero PRs classified"))
    return {
        "task_key": TASK_KEY,
        "conflict_domain": CONFLICT_DOMAIN,
        "inventory_version": INVENTORY_VERSION,
        "schema_version": SCHEMA_VERSION,
        "evidence_kind": EVIDENCE_KIND,
        "auto_close": AUTO_CLOSE,
        "mutations": list(MUTATION_ACTIONS),
        "classifications": list(CLASSES),
        "pr_count": len(rows),
        "unique_count": count_class(rows, CLASS_UNIQUE),
        "duplicate_count": count_class(rows, CLASS_DUPLICATE),
        "superseded_count": count_class(rows, CLASS_SUPERSEDED),
        "unknown_count": count_class(rows, CLASS_UNKNOWN),
        "records": [row.as_dict() for row in rows],
    }


def basename_overlap_is_not_a_cluster(left_files: Sequence[str], right_files: Sequence[str]) -> bool:
    """True when two file lists share a basename but not the full path set.

    Filename heuristics alone must not form a cluster. Callers still need a
    shared head, shared (title, files) pair, or an explicit title reference.
    """

    left = [Path(item).name for item in left_files]
    right = [Path(item).name for item in right_files]
    full_overlap = frozenset(left_files) == frozenset(right_files)
    return (not full_overlap) and bool(set(left) & set(right))


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=DEFAULT_FIXTURE,
        help="JSON fixture with schema_version and prs (defaults to the shipped table)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print the classification report as JSON",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        document = load_document(args.path)
        rows, errors = classify_document(document)
        report = report_from_rows(rows) if rows else None
    except DuplicateWorkAuditError as exc:
        print(f"duplicate-work-audit: {exc}", file=sys.stderr)
        return 1

    counts = {name: count_class(rows, name) for name in CLASSES}
    print(
        "duplicate-work-audit: "
        + ", ".join(f"{name}={counts[name]}" for name in CLASSES)
        + f" auto_close={str(AUTO_CLOSE).lower()} task={TASK_KEY}"
    )
    if args.json and report is not None:
        print(json.dumps(report, sort_keys=True, indent=2, separators=(",", ": ")))
    if errors:
        print("duplicate-work-audit failed:", file=sys.stderr)
        for item in errors:
            print(f"  {item}", file=sys.stderr)
        return 1
    if AUTO_CLOSE or MUTATION_ACTIONS:
        print("duplicate-work-audit: auto-close is forbidden", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
