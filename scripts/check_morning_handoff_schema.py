#!/usr/bin/env python3
"""Versioned fail-closed morning master-handoff skeleton (#969 S500).

Closed sections: shipped, validated, failed_closed, ready_next.
Every item requires a title and at least one evidence ref. Unknown
sections, unknown fields, and missing evidence fail closed.

Distinct from the S090 morning-summary *category* schema. Finding prefix:
``morning-handoff``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Mapping, Sequence


SCHEMA_VERSION = 1
TASK_KEY = "reserve-S500-morning-handoff"
CONFLICT_DOMAIN = "ops.morning_master_handoff"
SECTIONS: tuple[str, ...] = ("shipped", "validated", "failed_closed", "ready_next")
SECTION_SET = frozenset(SECTIONS)
DOCUMENT_FIELDS = frozenset({"schema_version", "window", "sections"})
ITEM_FIELDS = frozenset({"title", "evidence_refs"})
_FINDING_PREFIX = "morning-handoff"


def _error(code: str, message: str) -> str:
    return f"{_FINDING_PREFIX} {code}: {message}"


def validate_morning_handoff(document: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(document, Mapping):
        return [_error("unknown root_type", "morning handoff document must be an object")]

    unknown = set(document) - DOCUMENT_FIELDS
    if unknown:
        errors.append(
            _error(
                "unknown field",
                "document has unknown fields: " + ", ".join(sorted(str(item) for item in unknown)),
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
    window = document.get("window")
    if not isinstance(window, str) or not window.strip():
        errors.append(_error("missing_value window", "window must be a non-empty string"))

    sections = document.get("sections")
    if not isinstance(sections, Mapping):
        errors.append(_error("unknown sections_type", "sections must be an object"))
        return errors

    unknown_sections = set(sections) - SECTION_SET
    if unknown_sections:
        errors.append(
            _error(
                "unknown section",
                "unknown sections: " + ", ".join(sorted(str(item) for item in unknown_sections)),
            )
        )
    missing_sections = SECTION_SET - set(sections)
    if missing_sections:
        errors.append(
            _error(
                "missing_value section",
                "missing sections: " + ", ".join(sorted(missing_sections)),
            )
        )

    for name in SECTIONS:
        items = sections.get(name)
        if name not in sections:
            continue
        if not isinstance(items, list):
            errors.append(_error("unknown items_type", f"sections.{name} must be a list"))
            continue
        for index, item in enumerate(items):
            prefix = f"sections.{name}[{index}]"
            if not isinstance(item, Mapping):
                errors.append(_error("unknown item_type", f"{prefix} must be an object"))
                continue
            extra = set(item) - ITEM_FIELDS
            if extra:
                errors.append(
                    _error(
                        "unknown field",
                        f"{prefix} has unknown fields: " + ", ".join(sorted(str(field) for field in extra)),
                    )
                )
            title = item.get("title")
            if not isinstance(title, str) or not title.strip():
                errors.append(_error("missing_value title", f"{prefix} title must be a non-empty string"))
            refs = item.get("evidence_refs")
            if not isinstance(refs, list) or not refs:
                errors.append(
                    _error("missing_value evidence_refs", f"{prefix} evidence_refs must be a non-empty list")
                )
                continue
            for ref_index, ref in enumerate(refs):
                if not isinstance(ref, str) or not ref.strip():
                    errors.append(
                        _error(
                            "unknown evidence_ref",
                            f"{prefix} evidence_refs[{ref_index}] must be a non-empty string",
                        )
                    )
    return errors


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
    parser.add_argument("path", type=Path, help="morning-handoff JSON document")
    args = parser.parse_args(argv)
    errors = validate_morning_handoff(load_document(args.path))
    if errors:
        print("Morning-handoff schema validation failed:", file=sys.stderr)
        for item in errors:
            print(f"  {item}", file=sys.stderr)
        return 1
    print(f"Morning-handoff schema v{SCHEMA_VERSION} accepted {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
