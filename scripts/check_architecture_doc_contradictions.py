#!/usr/bin/env python3
"""Fail-closed architecture-doc contradiction inventory (#969 S181).

Classifies claims from a closed allowlist of architecture/consolidation docs.
Unknown verdicts, missing allowlisted files, and unreadable docs fail closed.
Cross-document collisions are inventory output (``contradicting``), not guessed
away. Unique finding prefix: ``doc-contradiction``.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]

DOC_ALLOWLIST: tuple[str, ...] = (
    "docs/ARCHITECTURE.md",
    "docs/CANONICAL_MODULE_BOUNDARIES.md",
    "docs/CONSOLIDATION.md",
    "docs/CONSOLIDATION_MATRIX.md",
)

CLAIM_KINDS: tuple[str, ...] = ("repo_disposition", "capability_owner")
ROW_STATUSES: tuple[str, ...] = (
    "consistent",
    "contradicting",
    "missing_value",
    "unreadable",
    "unknown",
)
DISPOSITION_CLASSES: tuple[str, ...] = (
    "canonical",
    "promote",
    "characterize",
    "quarantine",
    "inspect",
    "sibling",
    "archive",
    "delete",
    "narrative",
    "missing",
    "unknown",
)

_FINDING_PREFIX = "doc-contradiction"
_SPLIT_RE = re.compile(r"\s*(?:,|/|;|\band\b)\s*", re.IGNORECASE)
_TICK_RE = re.compile(r"`([^`]+)`")
_PATH_RE = re.compile(
    r"\b(?:skeleton|backend|frontend|core|docs|scripts)/[A-Za-z0-9_./-]*",
)
_BOLD_RE = re.compile(r"\*+")


@dataclass(frozen=True)
class Claim:
    kind: str
    key: str
    value: str
    source: str
    raw: str


def classify_disposition(text: str) -> str:
    """Map a verdict/disposition cell onto one closed class. Unknown fails closed."""

    if not isinstance(text, str):
        return "unknown"
    lowered = " ".join(text.lower().split())
    if not lowered:
        return "missing"
    rules: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("canonical", ("canonical", "survives")),
        ("promote", ("promote",)),
        ("characterize", ("characterize",)),
        ("quarantine", ("quarantine",)),
        ("inspect", ("inspect", "leave", "not gameforge")),
        ("sibling", ("sibling", "do not merge", "keep as sibling")),
        ("archive", ("archive", "superseded", "merged")),
        ("delete", ("delete", "redundant", "empty", "nothing to merge", "nothing to merge")),
    )
    hits = [cls for cls, needles in rules if any(needle in lowered for needle in needles)]
    unique = []
    for item in hits:
        if item not in unique:
            unique.append(item)
    if len(unique) == 1:
        return unique[0]
    if len(unique) > 1:
        # "Merged ... then archive" is still archive; "empty ... delete" is delete.
        if unique == ["archive"] or set(unique) <= {"archive"}:
            return "archive"
        if "archive" in unique and "delete" not in unique and "canonical" not in unique:
            return "archive"
        if "delete" in unique and "promote" not in unique and "canonical" not in unique:
            return "delete"
        return "unknown"
    if _PATH_RE.search(text) or _TICK_RE.search(text):
        return "narrative"
    return "unknown"


def normalize_repo_keys(cell: str) -> tuple[str, ...]:
    """Split a repository-family cell into comparable keys."""

    cleaned = _BOLD_RE.sub("", cell)
    cleaned = cleaned.replace("`", "")
    cleaned = re.sub(r"\([^)]*\)", " ", cleaned)
    parts = [part.strip().lower() for part in _SPLIT_RE.split(cleaned) if part.strip()]
    keys = []
    for part in parts:
        token = " ".join(part.split())
        if not token or token in {"see below", "see above"}:
            continue
        keys.append(token)
    return tuple(dict.fromkeys(keys))


def extract_owner_value(cell: str) -> str:
    ticks = [item.strip() for item in _TICK_RE.findall(cell) if item.strip()]
    paths = [item.strip().rstrip("/") + "/" for item in _PATH_RE.findall(cell)]
    tokens = tuple(dict.fromkeys([*ticks, *paths]))
    if not tokens:
        text = " ".join(cell.split())
        return text
    return "|".join(tokens)


def parse_markdown_tables(text: str) -> list[list[list[str]]]:
    tables: list[list[list[str]]] = []
    current: list[list[str]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith("|"):
            if current:
                tables.append(current)
                current = []
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if cells and all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in cells):
            continue
        current.append(cells)
    if current:
        tables.append(current)
    return tables


def _header_index(header: Sequence[str], *names: str) -> int | None:
    lowered = [cell.strip().lower() for cell in header]
    for name in names:
        if name in lowered:
            return lowered.index(name)
    return None


def _read_doc(root: Path, relative: str) -> tuple[str | None, str | None]:
    path = root / relative
    try:
        return path.read_text(encoding="utf-8"), None
    except FileNotFoundError:
        return None, f"{_FINDING_PREFIX} unreadable missing_doc: {relative}: allowlisted architecture doc is missing"
    except OSError as exc:
        return None, (
            f"{_FINDING_PREFIX} unreadable io_error: {relative}: "
            f"cannot inspect architecture doc: {type(exc).__name__}"
        )


def collect_claims(root: Path) -> tuple[list[Claim], list[str]]:
    claims: list[Claim] = []
    violations: list[str] = []
    for relative in DOC_ALLOWLIST:
        text, error = _read_doc(root, relative)
        if error is not None:
            violations.append(error)
            continue
        assert text is not None
        tables = parse_markdown_tables(text)
        for table in tables:
            if not table:
                continue
            header = table[0]
            repo_idx = _header_index(header, "repo", "repository family", "repository")
            verdict_idx = _header_index(header, "verdict", "initial disposition", "disposition")
            cap_idx = _header_index(header, "capability")
            owner_idx = _header_index(header, "canonical owner")
            if repo_idx is not None and verdict_idx is not None:
                for row in table[1:]:
                    if max(repo_idx, verdict_idx) >= len(row):
                        violations.append(
                            f"{_FINDING_PREFIX} unknown short_row: {relative}: "
                            "repo disposition table row is missing required columns"
                        )
                        continue
                    keys = normalize_repo_keys(row[repo_idx])
                    disposition = classify_disposition(row[verdict_idx])
                    if not keys:
                        violations.append(
                            f"{_FINDING_PREFIX} unknown empty_repo: {relative}: "
                            "repo disposition table row has no repository key"
                        )
                        continue
                    for key in keys:
                        claims.append(
                            Claim(
                                kind="repo_disposition",
                                key=key,
                                value=disposition,
                                source=relative,
                                raw=row[verdict_idx],
                            )
                        )
            if cap_idx is not None and owner_idx is not None:
                for row in table[1:]:
                    if max(cap_idx, owner_idx) >= len(row):
                        violations.append(
                            f"{_FINDING_PREFIX} unknown short_row: {relative}: "
                            "capability owner table row is missing required columns"
                        )
                        continue
                    capability = " ".join(_BOLD_RE.sub("", row[cap_idx]).lower().split())
                    if not capability:
                        violations.append(
                            f"{_FINDING_PREFIX} missing_value empty_capability: {relative}: "
                            "capability owner table row has an empty capability"
                        )
                        continue
                    owner = extract_owner_value(row[owner_idx])
                    value = "missing" if not owner else owner
                    claims.append(
                        Claim(
                            kind="capability_owner",
                            key=capability,
                            value=value,
                            source=relative,
                            raw=row[owner_idx],
                        )
                    )
    return claims, violations


def _grouped(claims: Iterable[Claim]) -> dict[tuple[str, str], list[Claim]]:
    grouped: dict[tuple[str, str], list[Claim]] = defaultdict(list)
    for claim in claims:
        grouped[(claim.kind, claim.key)].append(claim)
    return grouped


def inventory_rows(claims: Sequence[Claim]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for (kind, key), group in sorted(_grouped(claims).items()):
        values = tuple(dict.fromkeys(claim.value for claim in group))
        sources = tuple(dict.fromkeys(claim.source for claim in group))
        if any(value == "unknown" for value in values):
            status = "unknown"
        elif any(value in {"missing", "missing_value"} for value in values) and len(values) == 1:
            status = "missing_value"
        elif len(values) == 1:
            status = "consistent"
        else:
            status = "contradicting"
        rows.append(
            {
                "kind": kind,
                "key": key,
                "status": status,
                "values": list(values),
                "sources": list(sources),
            }
        )
    return rows


def collect_violations(root: Path) -> list[str]:
    claims, violations = collect_claims(root)
    for row in inventory_rows(claims):
        if row["status"] == "unknown":
            violations.append(
                f"{_FINDING_PREFIX} unknown unclassified: {row['kind']}:{row['key']}: "
                f"values={row['values']} sources={row['sources']}"
            )
        if row["status"] == "missing_value":
            violations.append(
                f"{_FINDING_PREFIX} missing_value empty_claim: {row['kind']}:{row['key']}: "
                f"sources={row['sources']}"
            )
    return sorted(violations)


def render_report(rows: Sequence[Mapping[str, object]]) -> str:
    contradicting = [row for row in rows if row["status"] == "contradicting"]
    consistent = [row for row in rows if row["status"] == "consistent"]
    lines = [
        (
            f"Architecture-doc contradiction inventory classified {len(rows)} claims: "
            f"{len(consistent)} consistent, {len(contradicting)} contradicting, "
            f"{sum(1 for row in rows if row['status'] not in {'consistent', 'contradicting'})} other."
        )
    ]
    for row in contradicting:
        lines.append(
            f"  contradicting: {_FINDING_PREFIX} contradicting {row['kind']}: {row['key']}: "
            f"{', '.join(str(item) for item in row['values'])} "
            f"({', '.join(str(item) for item in row['sources'])})"
        )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(REPO_ROOT), help="repository root")
    args = parser.parse_args(argv)
    root = Path(args.root)
    claims, read_errors = collect_claims(root)
    rows = inventory_rows(claims)
    violations = collect_violations(root)
    # collect_violations re-reads; keep read_errors if we short-circuit — they are included.
    del read_errors
    print(render_report(rows))
    if violations:
        print("Architecture-doc contradiction inventory failed:", file=sys.stderr)
        for item in violations:
            print(f"  {item}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
