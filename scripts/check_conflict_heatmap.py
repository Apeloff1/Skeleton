#!/usr/bin/env python3
"""Fail-closed path-derived conflict heatmap (#969 Seed 31).

Reads a fixture of write surfaces ``{path, pr, updated}`` and rolls them up
into heatmap cells using the same two-segment path key the shift supervisor
uses for conflict domains. Closed classes:

* busy — a positive PR updated inside the recency window; too busy for
  another squad
* idle — every classified write on the cell is outside the window or has
  no occupying PR
* unknown — the surface or cell cannot be classified (always a gate failure)

Unobserved cells stay unknown: absence of evidence is not idle. This checker
classifies JSON only. It never opens PRs, never mutates leases, and does not
own named-task reconciliation (S492) or saturation metrics (S400).

Finding prefix: ``conflict-heatmap``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence


SCHEMA_VERSION = 1
TASK_KEY = "reserve-S495-conflict-heatmap"
CONFLICT_DOMAIN = "ops.readonly.conflict_heatmap"
CLASSES: tuple[str, ...] = ("busy", "idle", "unknown")
CLASS_SET = frozenset(CLASSES)
DOCUMENT_FIELDS = frozenset({"schema_version", "as_of", "busy_window_seconds", "surfaces"})
SURFACE_FIELDS = frozenset({"path", "pr", "updated"})
_FINDING_PREFIX = "conflict-heatmap"
_UTC_STAMP = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})T(?P<hms>\d{2}:\d{2}:\d{2})(?P<frac>\.\d{1,9})?(?:Z|[+]00:00|[-]00:00)$"
)
_PATH_SEGMENT = re.compile(r"^[A-Za-z0-9._-]+$")


def _error(code: str, message: str) -> str:
    return f"{_FINDING_PREFIX} {code}: {message}"


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def parse_utc(value: object) -> datetime | None:
    """Parse an explicit UTC stamp. Naive and non-UTC offsets stay unknown."""

    if not isinstance(value, str):
        return None
    text = value.strip()
    match = _UTC_STAMP.fullmatch(text)
    if match is None:
        return None
    frac = match.group("frac") or ""
    iso = f"{match.group('date')}T{match.group('hms')}{frac}+00:00"
    try:
        stamp = datetime.fromisoformat(iso)
    except ValueError:
        return None
    if stamp.tzinfo is None:
        return None
    return stamp.astimezone(timezone.utc)


def canonical_write_path(value: object) -> str | None:
    """Return a repo-relative POSIX path, or None when the path is not evidence."""

    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or "\x00" in text or "\\" in text:
        return None
    if text.startswith("/") or text.startswith("./") or text.endswith("/"):
        return None
    if "//" in text:
        return None
    parts = text.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        return None
    if any(_PATH_SEGMENT.fullmatch(part) is None for part in parts):
        return None
    return "/".join(parts)


def derive_conflict_cell(path: str) -> str:
    """Map a canonical path onto the two-segment conflict cell."""

    parts = path.split("/")
    return "/".join(parts[:2])


def squad_may_enter(classification: str) -> bool:
    """Another squad may enter only an idle cell. Unknown fails closed."""

    return classification == "idle"


def _rank(classification: str) -> int:
    # unknown dominates (fail closed), then busy, then idle.
    return {"unknown": 0, "busy": 1, "idle": 2}[classification]


@dataclass(frozen=True)
class SurfaceRow:
    index: int
    path: str | None
    cell: str | None
    pr: int | None
    updated: str | None
    classification: str
    age_seconds: int | None


@dataclass(frozen=True)
class HeatCell:
    key: str
    classification: str
    paths: tuple[str, ...]
    prs: tuple[int, ...]
    newest: str | None
    surface_indexes: tuple[int, ...]


@dataclass(frozen=True)
class HeatmapReport:
    cells: tuple[HeatCell, ...]
    surfaces: tuple[SurfaceRow, ...]
    errors: tuple[str, ...]

    @property
    def counts(self) -> dict[str, int]:
        tallies = {name: 0 for name in CLASSES}
        for cell in self.cells:
            tallies[cell.classification] += 1
        return tallies


def classify_surface(
    record: object,
    *,
    as_of: datetime | None,
    window_seconds: int | None,
    index: int,
) -> tuple[SurfaceRow, list[str]]:
    """Classify one ``{path, pr, updated}`` write surface."""

    errors: list[str] = []
    label = f"surfaces[{index}]"
    if not isinstance(record, Mapping):
        errors.append(_error("unknown surface_type", f"{label} must be an object"))
        return (
            SurfaceRow(index, None, None, None, None, "unknown", None),
            errors,
        )

    extra = set(record) - SURFACE_FIELDS
    if extra:
        errors.append(
            _error(
                "unknown field",
                f"{label} has unknown fields: " + ", ".join(sorted(str(item) for item in extra)),
            )
        )
    missing = SURFACE_FIELDS - set(record)
    if missing:
        errors.append(
            _error(
                "missing_value field",
                f"{label} missing fields: " + ", ".join(sorted(missing)),
            )
        )

    path = canonical_write_path(record.get("path"))
    if path is None:
        errors.append(_error("unknown path", f"{label}.path must be a canonical repo-relative POSIX path"))

    pr_raw = record.get("pr")
    pr: int | None
    if pr_raw is None:
        pr = None
    elif _is_int(pr_raw) and pr_raw > 0:
        pr = pr_raw
    else:
        pr = None
        errors.append(_error("unknown pr", f"{label}.pr must be null or a positive integer"))

    updated_raw = record.get("updated")
    updated = parse_utc(updated_raw)
    if updated is None:
        errors.append(_error("unknown updated", f"{label}.updated must be an explicit UTC RFC3339 stamp"))

    age: int | None = None
    classification = "unknown"
    if errors:
        classification = "unknown"
    elif as_of is None or window_seconds is None or path is None or updated is None:
        classification = "unknown"
        errors.append(_error("unknown clock", f"{label} cannot be aged without as_of and busy_window_seconds"))
    elif updated > as_of:
        classification = "unknown"
        errors.append(_error("unknown future_write", f"{label}.updated is after as_of"))
    else:
        age = int((as_of - updated).total_seconds())
        recent = age <= window_seconds
        if recent and pr is not None:
            classification = "busy"
        else:
            classification = "idle"

    cell = derive_conflict_cell(path) if path is not None else None
    updated_text = updated_raw.strip() if isinstance(updated_raw, str) else None
    return SurfaceRow(index, path, cell, pr, updated_text, classification, age), errors


def classify_heatmap(document: object) -> HeatmapReport:
    """Build the path-derived heatmap. Unknown cells are violations."""

    errors: list[str] = []
    if not isinstance(document, Mapping):
        return HeatmapReport((), (), (_error("unknown root_type", "conflict heatmap document must be an object"),))

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

    as_of = parse_utc(document.get("as_of"))
    if as_of is None:
        errors.append(_error("unknown as_of", "as_of must be an explicit UTC RFC3339 stamp"))

    window = document.get("busy_window_seconds")
    if not _is_int(window) or window < 0:
        errors.append(_error("unknown window", "busy_window_seconds must be an integer >= 0"))
        window = None

    surfaces_raw = document.get("surfaces")
    if not isinstance(surfaces_raw, list):
        errors.append(_error("unknown surfaces_type", "surfaces must be a list"))
        return HeatmapReport((), (), tuple(errors))

    rows: list[SurfaceRow] = []
    for index, record in enumerate(surfaces_raw):
        row, row_errors = classify_surface(
            record, as_of=as_of, window_seconds=window, index=index
        )
        rows.append(row)
        errors.extend(row_errors)
        if row.classification == "unknown" and not row_errors:
            errors.append(_error("unknown unclassified", f"surfaces[{index}] could not be classified"))

    buckets: dict[str, list[SurfaceRow]] = {}
    for row in rows:
        if row.cell is None:
            continue
        buckets.setdefault(row.cell, []).append(row)

    cells: list[HeatCell] = []
    for key in sorted(buckets):
        members = buckets[key]
        classification = min((row.classification for row in members), key=_rank)
        paths = tuple(sorted({row.path for row in members if row.path}))
        prs = tuple(sorted({row.pr for row in members if row.pr is not None}))
        dated = [row for row in members if row.updated and row.classification != "unknown"]
        newest = max((row.updated for row in dated), default=None) if dated else None
        cells.append(
            HeatCell(
                key=key,
                classification=classification,
                paths=paths,
                prs=prs,
                newest=newest,
                surface_indexes=tuple(row.index for row in members),
            )
        )
        if classification == "unknown":
            errors.append(_error("unknown cell", f"cell {key!r} is unknown and fails closed"))

    return HeatmapReport(tuple(cells), tuple(rows), tuple(errors))


def lookup_cell(report: HeatmapReport, path: object) -> str:
    """Classify a proposed write path against the heatmap. Missing cells are unknown."""

    canonical = canonical_write_path(path)
    if canonical is None:
        return "unknown"
    key = derive_conflict_cell(canonical)
    for cell in report.cells:
        if cell.key == key:
            return cell.classification
    return "unknown"


def load_document(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(_error("unreadable missing_doc", f"{path} is missing")) from exc
    except OSError as exc:
        raise SystemExit(_error("unreadable io_error", f"cannot read {path}: {type(exc).__name__}")) from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(
            _error("unreadable json", f"invalid JSON in {path} at line {exc.lineno}, column {exc.colno}")
        ) from exc


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="conflict-heatmap JSON fixture of {path, pr, updated}")
    args = parser.parse_args(argv)
    report = classify_heatmap(load_document(args.path))
    counts = report.counts
    print(
        "Conflict heatmap: "
        + ", ".join(f"{name}={counts[name]}" for name in CLASSES)
        + f" cells={len(report.cells)}"
    )
    for cell in report.cells:
        prs = ",".join(str(item) for item in cell.prs) or "-"
        newest = cell.newest or "-"
        print(f"  {cell.key}  {cell.classification}  prs={prs}  newest={newest}")
    if report.errors:
        print("Conflict heatmap failed:", file=sys.stderr)
        for item in report.errors:
            print(f"  {item}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
