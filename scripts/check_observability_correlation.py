#!/usr/bin/env python3
"""Fail-closed observability correlation-ID inventory (#969 Seed 18 / #960 S085).

Classifies fixture hops across API/runtime/agent/tool/storage/evidence paths.
Closed classes:

* correlated — hop carries a canonical correlation id shared with the document
* gap — hop is a known path class but the id is absent or mismatched
* unknown — path class, hop shape, or id cannot be classified (always a gate failure)

Unknown is never guessed as correlated. Missing ids, extra fields, unknown path
classes, and unreadable documents fail closed. This checker classifies JSON only.

Finding prefix: ``observability-correlation``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from typing import Mapping, Sequence


SCHEMA_VERSION = 1
TASK_ID = "reserve-S085-correlation-audit"
CONFLICT_DOMAIN = "observability.readonly.correlation"
CLASSES: tuple[str, ...] = ("correlated", "gap", "unknown")
CLASS_SET = frozenset(CLASSES)
PATH_CLASSES: tuple[str, ...] = (
    "api",
    "runtime",
    "agent",
    "tool",
    "storage",
    "evidence",
)
PATH_CLASS_SET = frozenset(PATH_CLASSES)
DOCUMENT_FIELDS = frozenset({"schema_version", "correlation_id", "hops"})
HOP_FIELDS = frozenset({"path_class", "surface", "correlation_id"})
_FINDING_PREFIX = "observability-correlation"
_CORRELATION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")


def _error(code: str, message: str) -> str:
    return f"{_FINDING_PREFIX} {code}: {message}"


def canonical_correlation_id(value: object) -> str | None:
    """Return a canonical correlation id, or None when the value is not evidence."""

    if not isinstance(value, str):
        return None
    text = value.strip()
    if _CORRELATION_ID.fullmatch(text) is None:
        return None
    return text


def canonical_surface(value: object) -> str | None:
    """Repo-relative or dotted surface name. Empty/path-escape values are unknown."""

    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or "\x00" in text or "\\" in text:
        return None
    if text.startswith("/") or text.startswith("./") or "//" in text:
        return None
    parts = text.replace(".", "/").split("/")
    if any(part in {"", ".", ".."} for part in parts):
        return None
    return text


@dataclass(frozen=True)
class HopRow:
    index: int
    path_class: str | None
    surface: str | None
    correlation_id: str | None
    classification: str


@dataclass(frozen=True)
class CorrelationReport:
    hops: tuple[HopRow, ...]
    errors: tuple[str, ...]
    document_id: str | None

    @property
    def counts(self) -> dict[str, int]:
        counts = {name: 0 for name in CLASSES}
        for hop in self.hops:
            counts[hop.classification] += 1
        return counts


def classify_hop(
    record: object,
    *,
    document_id: str | None,
    index: int,
) -> tuple[HopRow, tuple[str, ...]]:
    errors: list[str] = []
    label = f"hops[{index}]"
    if not isinstance(record, Mapping):
        errors.append(_error("unknown hop_type", f"{label} must be an object"))
        return HopRow(index, None, None, None, "unknown"), tuple(errors)

    extra = set(record) - HOP_FIELDS
    if extra:
        errors.append(
            _error(
                "unknown field",
                f"{label} has unknown fields: " + ", ".join(sorted(str(item) for item in extra)),
            )
        )
    missing = HOP_FIELDS - set(record)
    if missing:
        errors.append(
            _error(
                "missing_value field",
                f"{label} missing fields: " + ", ".join(sorted(missing)),
            )
        )

    path_class_raw = record.get("path_class")
    path_class: str | None
    if isinstance(path_class_raw, str) and path_class_raw.strip() in PATH_CLASS_SET:
        path_class = path_class_raw.strip()
    else:
        path_class = None
        errors.append(
            _error(
                "unknown path_class",
                f"{label}.path_class must be one of " + ", ".join(PATH_CLASSES),
            )
        )

    surface = canonical_surface(record.get("surface"))
    if surface is None:
        errors.append(_error("unknown surface", f"{label}.surface must be a non-empty surface name"))

    hop_id = canonical_correlation_id(record.get("correlation_id"))
    raw_id = record.get("correlation_id")
    if raw_id is None:
        hop_id = None
    elif hop_id is None:
        errors.append(
            _error(
                "unknown correlation_id",
                f"{label}.correlation_id must be a canonical id or null",
            )
        )

    if errors:
        classification = "unknown"
    elif document_id is None:
        classification = "unknown"
        errors.append(_error("unknown document_id", f"{label} cannot correlate without a document id"))
    elif hop_id is None:
        classification = "gap"
    elif hop_id != document_id:
        classification = "gap"
    else:
        classification = "correlated"

    return HopRow(index, path_class, surface, hop_id, classification), tuple(errors)


def classify_correlation(document: object) -> CorrelationReport:
    """Classify hops. Unknown and gap fail the gate; correlated alone is accepted."""

    if not isinstance(document, Mapping):
        return CorrelationReport((), (_error("unknown root_type", "correlation document must be an object"),), None)

    errors: list[str] = []
    extra = set(document) - DOCUMENT_FIELDS
    if extra:
        errors.append(
            _error(
                "unknown field",
                "document has unknown fields: " + ", ".join(sorted(str(item) for item in extra)),
            )
        )
    missing = DOCUMENT_FIELDS - set(document)
    if missing:
        errors.append(
            _error(
                "missing_value field",
                "document missing fields: " + ", ".join(sorted(missing)),
            )
        )

    if document.get("schema_version") != SCHEMA_VERSION:
        errors.append(_error("unknown schema_version", f"schema_version must be exactly {SCHEMA_VERSION}"))

    document_id = canonical_correlation_id(document.get("correlation_id"))
    if document_id is None:
        errors.append(
            _error(
                "unknown correlation_id",
                "document.correlation_id must be a canonical correlation id",
            )
        )

    hops_raw = document.get("hops")
    if not isinstance(hops_raw, list):
        errors.append(_error("unknown hops_type", "hops must be a list"))
        return CorrelationReport((), tuple(errors), document_id)
    if not hops_raw:
        errors.append(_error("unknown hops_empty", "hops must cover at least one path class"))

    rows: list[HopRow] = []
    seen_classes: set[str] = set()
    for index, record in enumerate(hops_raw):
        row, row_errors = classify_hop(record, document_id=document_id, index=index)
        rows.append(row)
        errors.extend(row_errors)
        if row.path_class is not None:
            if row.path_class in seen_classes:
                errors.append(
                    _error(
                        "unknown duplicate_path_class",
                        f"hops[{index}] duplicates path_class {row.path_class!r}",
                    )
                )
                if row.classification != "unknown":
                    rows[-1] = HopRow(row.index, row.path_class, row.surface, row.correlation_id, "unknown")
            seen_classes.add(row.path_class)
        if row.classification == "unknown" and not row_errors:
            errors.append(_error("unknown unclassified", f"hops[{index}] could not be classified"))

    covered = {row.path_class for row in rows if row.path_class in PATH_CLASS_SET}
    missing_classes = [name for name in PATH_CLASSES if name not in covered]
    if missing_classes:
        errors.append(
            _error(
                "unknown path_class_coverage",
                "missing path classes: " + ", ".join(missing_classes),
            )
        )

    if any(row.classification == "gap" for row in rows):
        errors.append(_error("gap hop", "at least one hop is missing or mismatched correlation evidence"))

    return CorrelationReport(tuple(rows), tuple(errors), document_id)


def load_document(path) -> object:
    from pathlib import Path

    target = Path(path)
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(_error("unreadable missing_doc", f"{target} is missing")) from exc
    except OSError as exc:
        raise SystemExit(_error("unreadable io_error", f"cannot read {target}: {type(exc).__name__}")) from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(
            _error("unreadable json", f"invalid JSON in {target} at line {exc.lineno}, column {exc.colno}")
        ) from exc


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="correlation-audit JSON fixture of {correlation_id, hops}")
    args = parser.parse_args(argv)
    report = classify_correlation(load_document(args.path))
    counts = report.counts
    print(
        "Observability correlation: "
        + ", ".join(f"{name}={counts[name]}" for name in CLASSES)
    )
    for hop in report.hops:
        hop_id = hop.correlation_id or "-"
        path_class = hop.path_class or "-"
        surface = hop.surface or "-"
        print(f"  {path_class}  {hop.classification}  surface={surface}  id={hop_id}")
    if report.errors:
        print("Observability correlation failed:", file=sys.stderr)
        for item in report.errors:
            print(f"  {item}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
