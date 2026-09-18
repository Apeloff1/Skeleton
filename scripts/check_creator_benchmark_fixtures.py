#!/usr/bin/env python3
"""Fail-closed creator-intent benchmark fixtures (#969 S039).

Conflict domain: ``eval.fixtures.creator_intent``. These are small,
provider-free concept fixtures plus expected normalized and design-graph
constraints. The checker is stdlib-only: it does not compile intents, score
concept-to-release runs, call model providers, or import ``skeleton.creator``
/ ``skeleton.eval``.

Unknown fixture fields, unknown ops/kinds, dangling graph refs, and
non-canonical identifiers fail closed. Unique prefix: ``creator-intent-fixture``.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

TASK_KEY = "reserve-S039-creator-benchmark-fixtures"
CONFLICT_DOMAIN = "eval.fixtures.creator_intent"
SCHEMA = "eval.fixtures.creator_intent.v1"
SCHEMA_VERSION = 1
FIXTURE_DIR = Path("eval/fixtures/creator_intent")

DOCUMENT_FIELDS = frozenset(
    {
        "schema",
        "schema_version",
        "fixture_id",
        "concept",
        "expected_normalized",
        "expected_design_graph",
    }
)
CONCEPT_FIELDS = frozenset({"title", "statement"})
NORMALIZED_FIELDS = frozenset({"constraints"})
DESIGN_GRAPH_FIELDS = frozenset({"nodes", "constraints"})
CONSTRAINT_FIELDS = frozenset({"id", "field", "op", "value"})
GRAPH_CONSTRAINT_FIELDS = frozenset({"id", "applies_to"})
NODE_FIELDS = frozenset({"id", "kind", "title", "depends_on"})

CONSTRAINT_OPS = frozenset({"require", "forbid", "equals", "min", "max"})
NODE_KINDS = frozenset(
    {"concept", "system", "mechanic", "content", "world", "interface", "validation"}
)

MAX_TITLE_CHARS = 120
MAX_TEXT_CHARS = 512
MAX_CONSTRAINTS = 16
MAX_NODES = 16
MAX_DEPENDENCIES = 8
MAX_APPLIES_TO = 8
MAX_CATALOG_FILES = 32

_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_FILENAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*\.json$")
_FINDING_PREFIX = "creator-intent-fixture"


def _error(code: str, message: str) -> str:
    return f"{_FINDING_PREFIX} {code}: {message}"


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _token(value: object, *, maximum: int) -> str | None:
    if not isinstance(value, str) or not value.strip() or value.strip() != value:
        return None
    if len(value) > maximum:
        return None
    return value


def _identifier(value: object) -> str | None:
    token = _token(value, maximum=64)
    if token is None or not _ID_PATTERN.fullmatch(token):
        return None
    return token


def _json_scalar(value: object) -> bool:
    if value is None or isinstance(value, (bool, str)):
        return True
    if _is_int(value):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    return False


def _unknown_fields(payload: Mapping[object, object], allowed: frozenset[str], *, where: str) -> str | None:
    extra = sorted(str(key) for key in payload if key not in allowed)
    if extra:
        return _error("unknown field", f"{where} has unknown fields: " + ", ".join(extra))
    return None


def _missing_fields(payload: Mapping[object, object], allowed: frozenset[str], *, where: str) -> str | None:
    missing = sorted(field for field in allowed if field not in payload)
    if missing:
        return _error(
            "missing_value field",
            f"{where} missing fields: " + ", ".join(missing),
        )
    return None


def _require_mapping(value: object, *, where: str, errors: list[str]) -> Mapping[object, object] | None:
    if not isinstance(value, Mapping):
        errors.append(_error("unknown type", f"{where} must be an object"))
        return None
    return value


def _require_list(value: object, *, where: str, errors: list[str]) -> Sequence[object] | None:
    if isinstance(value, (str, bytes, bytearray, Mapping)) or not isinstance(value, Sequence):
        errors.append(_error("unknown type", f"{where} must be a list"))
        return None
    return value


def _validate_constraint(item: object, *, where: str, errors: list[str]) -> str | None:
    payload = _require_mapping(item, where=where, errors=errors)
    if payload is None:
        return None
    unknown = _unknown_fields(payload, CONSTRAINT_FIELDS, where=where)
    if unknown:
        errors.append(unknown)
    missing = _missing_fields(payload, CONSTRAINT_FIELDS, where=where)
    if missing:
        errors.append(missing)

    constraint_id = _identifier(payload.get("id"))
    if constraint_id is None:
        errors.append(_error("unknown identifier", f"{where}.id must be a canonical identifier"))
    field = _identifier(payload.get("field"))
    if field is None:
        errors.append(_error("unknown identifier", f"{where}.field must be a canonical identifier"))
    op = payload.get("op")
    if op not in CONSTRAINT_OPS:
        errors.append(_error("unknown op", f"{where}.op {op!r} is not in the closed set"))
    value = payload.get("value")
    if "value" in payload and not _json_scalar(value):
        errors.append(_error("unknown type", f"{where}.value must be a finite JSON scalar"))
    if op in {"min", "max"} and "value" in payload:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            errors.append(_error("unknown type", f"{where}.value must be numeric for {op}"))
        elif isinstance(value, float) and not math.isfinite(value):
            errors.append(_error("unknown type", f"{where}.value must be finite for {op}"))
    return constraint_id


def _validate_node(item: object, *, where: str, errors: list[str]) -> tuple[str | None, tuple[str, ...]]:
    payload = _require_mapping(item, where=where, errors=errors)
    if payload is None:
        return None, ()
    unknown = _unknown_fields(payload, NODE_FIELDS, where=where)
    if unknown:
        errors.append(unknown)
    missing = _missing_fields(payload, NODE_FIELDS, where=where)
    if missing:
        errors.append(missing)

    node_id = _identifier(payload.get("id"))
    if node_id is None:
        errors.append(_error("unknown identifier", f"{where}.id must be a canonical identifier"))
    kind = payload.get("kind")
    if kind not in NODE_KINDS:
        errors.append(_error("unknown kind", f"{where}.kind {kind!r} is not in the closed set"))
    title = _token(payload.get("title"), maximum=MAX_TITLE_CHARS)
    if title is None:
        errors.append(
            _error("missing_value title", f"{where}.title must be a trimmed non-empty string")
        )

    depends_raw = payload.get("depends_on")
    depends_on: list[str] = []
    listed = _require_list(depends_raw, where=f"{where}.depends_on", errors=errors)
    if listed is not None:
        if len(listed) > MAX_DEPENDENCIES:
            errors.append(
                _error(
                    "unknown bound",
                    f"{where}.depends_on exceeds {MAX_DEPENDENCIES} entries",
                )
            )
        seen: set[str] = set()
        for index, dep in enumerate(listed):
            dep_id = _identifier(dep)
            if dep_id is None:
                errors.append(
                    _error(
                        "unknown identifier",
                        f"{where}.depends_on[{index}] must be a canonical identifier",
                    )
                )
                continue
            if dep_id in seen:
                errors.append(
                    _error("unknown duplicate", f"{where}.depends_on repeats {dep_id}")
                )
            seen.add(dep_id)
            depends_on.append(dep_id)
        if node_id is not None and node_id in seen:
            errors.append(_error("unknown cycle", f"{where} depends on itself"))
    return node_id, tuple(depends_on)


def _validate_graph_constraint(item: object, *, where: str, errors: list[str]) -> tuple[str | None, tuple[str, ...]]:
    payload = _require_mapping(item, where=where, errors=errors)
    if payload is None:
        return None, ()
    unknown = _unknown_fields(payload, GRAPH_CONSTRAINT_FIELDS, where=where)
    if unknown:
        errors.append(unknown)
    missing = _missing_fields(payload, GRAPH_CONSTRAINT_FIELDS, where=where)
    if missing:
        errors.append(missing)

    constraint_id = _identifier(payload.get("id"))
    if constraint_id is None:
        errors.append(_error("unknown identifier", f"{where}.id must be a canonical identifier"))

    applies_raw = payload.get("applies_to")
    applies_to: list[str] = []
    listed = _require_list(applies_raw, where=f"{where}.applies_to", errors=errors)
    if listed is not None:
        if not listed:
            errors.append(
                _error("missing_value applies_to", f"{where}.applies_to must be a non-empty list")
            )
        if len(listed) > MAX_APPLIES_TO:
            errors.append(
                _error(
                    "unknown bound",
                    f"{where}.applies_to exceeds {MAX_APPLIES_TO} entries",
                )
            )
        seen: set[str] = set()
        for index, node_id in enumerate(listed):
            token = _identifier(node_id)
            if token is None:
                errors.append(
                    _error(
                        "unknown identifier",
                        f"{where}.applies_to[{index}] must be a canonical identifier",
                    )
                )
                continue
            if token in seen:
                errors.append(
                    _error("unknown duplicate", f"{where}.applies_to repeats {token}")
                )
            seen.add(token)
            applies_to.append(token)
    return constraint_id, tuple(applies_to)


def _detect_cycles(edges: Mapping[str, Sequence[str]]) -> tuple[str, ...] | None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def walk(node: str, stack: list[str]) -> tuple[str, ...] | None:
        if node in visiting:
            start = stack.index(node)
            return tuple(stack[start:] + [node])
        if node in visited:
            return None
        visiting.add(node)
        stack.append(node)
        for nxt in edges.get(node, ()):
            if nxt not in edges:
                continue
            cycle = walk(nxt, stack)
            if cycle is not None:
                return cycle
        stack.pop()
        visiting.remove(node)
        visited.add(node)
        return None

    for node in edges:
        cycle = walk(node, [])
        if cycle is not None:
            return cycle
    return None


def validate_creator_intent_fixture(document: object) -> list[str]:
    """Return fail-closed violations for one creator-intent fixture document."""

    errors: list[str] = []
    if not isinstance(document, Mapping):
        return [_error("unknown root_type", "creator intent fixture must be an object")]

    unknown = _unknown_fields(document, DOCUMENT_FIELDS, where="document")
    if unknown:
        errors.append(unknown)
    missing = _missing_fields(document, DOCUMENT_FIELDS, where="document")
    if missing:
        errors.append(missing)

    if document.get("schema") != SCHEMA:
        errors.append(
            _error("unknown schema", f"schema must be exactly {SCHEMA}")
        )

    version = document.get("schema_version")
    if version != SCHEMA_VERSION or not _is_int(version):
        errors.append(
            _error(
                "unknown schema_version",
                f"schema_version must be exactly {SCHEMA_VERSION}",
            )
        )

    fixture_id = _identifier(document.get("fixture_id"))
    if fixture_id is None:
        errors.append(
            _error("unknown identifier", "fixture_id must be a canonical identifier")
        )

    concept = _require_mapping(document.get("concept"), where="concept", errors=errors)
    if concept is not None:
        unknown_concept = _unknown_fields(concept, CONCEPT_FIELDS, where="concept")
        if unknown_concept:
            errors.append(unknown_concept)
        missing_concept = _missing_fields(concept, CONCEPT_FIELDS, where="concept")
        if missing_concept:
            errors.append(missing_concept)
        if _token(concept.get("title"), maximum=MAX_TITLE_CHARS) is None:
            errors.append(
                _error("missing_value title", "concept.title must be a trimmed non-empty string")
            )
        if _token(concept.get("statement"), maximum=MAX_TEXT_CHARS) is None:
            errors.append(
                _error(
                    "missing_value statement",
                    "concept.statement must be a trimmed non-empty string",
                )
            )

    normalized_ids: set[str] = set()
    normalized = _require_mapping(
        document.get("expected_normalized"), where="expected_normalized", errors=errors
    )
    if normalized is not None:
        unknown_norm = _unknown_fields(normalized, NORMALIZED_FIELDS, where="expected_normalized")
        if unknown_norm:
            errors.append(unknown_norm)
        missing_norm = _missing_fields(normalized, NORMALIZED_FIELDS, where="expected_normalized")
        if missing_norm:
            errors.append(missing_norm)
        constraints = _require_list(
            normalized.get("constraints"),
            where="expected_normalized.constraints",
            errors=errors,
        )
        if constraints is not None:
            if not constraints:
                errors.append(
                    _error(
                        "missing_value constraints",
                        "expected_normalized.constraints must be a non-empty list",
                    )
                )
            if len(constraints) > MAX_CONSTRAINTS:
                errors.append(
                    _error(
                        "unknown bound",
                        f"expected_normalized.constraints exceeds {MAX_CONSTRAINTS} entries",
                    )
                )
            for index, item in enumerate(constraints):
                constraint_id = _validate_constraint(
                    item, where=f"expected_normalized.constraints[{index}]", errors=errors
                )
                if constraint_id is None:
                    continue
                if constraint_id in normalized_ids:
                    errors.append(
                        _error(
                            "unknown duplicate",
                            f"expected_normalized.constraints repeats id {constraint_id}",
                        )
                    )
                normalized_ids.add(constraint_id)

    node_ids: set[str] = set()
    edges: dict[str, tuple[str, ...]] = {}
    graph = _require_mapping(
        document.get("expected_design_graph"),
        where="expected_design_graph",
        errors=errors,
    )
    if graph is not None:
        unknown_graph = _unknown_fields(graph, DESIGN_GRAPH_FIELDS, where="expected_design_graph")
        if unknown_graph:
            errors.append(unknown_graph)
        missing_graph = _missing_fields(graph, DESIGN_GRAPH_FIELDS, where="expected_design_graph")
        if missing_graph:
            errors.append(missing_graph)

        nodes = _require_list(
            graph.get("nodes"), where="expected_design_graph.nodes", errors=errors
        )
        if nodes is not None:
            if not nodes:
                errors.append(
                    _error(
                        "missing_value nodes",
                        "expected_design_graph.nodes must be a non-empty list",
                    )
                )
            if len(nodes) > MAX_NODES:
                errors.append(
                    _error(
                        "unknown bound",
                        f"expected_design_graph.nodes exceeds {MAX_NODES} entries",
                    )
                )
            for index, item in enumerate(nodes):
                node_id, depends_on = _validate_node(
                    item, where=f"expected_design_graph.nodes[{index}]", errors=errors
                )
                if node_id is None:
                    continue
                if node_id in node_ids:
                    errors.append(
                        _error(
                            "unknown duplicate",
                            f"expected_design_graph.nodes repeats id {node_id}",
                        )
                    )
                node_ids.add(node_id)
                edges[node_id] = depends_on

            for node_id, depends_on in edges.items():
                for dep in depends_on:
                    if dep not in node_ids:
                        errors.append(
                            _error(
                                "unknown dangling",
                                f"node {node_id} depends_on unknown node {dep}",
                            )
                        )
            cycle = _detect_cycles(edges)
            if cycle is not None:
                errors.append(
                    _error("unknown cycle", "design-graph depends_on cycle: " + " -> ".join(cycle))
                )

        graph_constraints = _require_list(
            graph.get("constraints"),
            where="expected_design_graph.constraints",
            errors=errors,
        )
        if graph_constraints is not None:
            if not graph_constraints:
                errors.append(
                    _error(
                        "missing_value constraints",
                        "expected_design_graph.constraints must be a non-empty list",
                    )
                )
            if len(graph_constraints) > MAX_CONSTRAINTS:
                errors.append(
                    _error(
                        "unknown bound",
                        f"expected_design_graph.constraints exceeds {MAX_CONSTRAINTS} entries",
                    )
                )
            seen_graph_ids: set[str] = set()
            for index, item in enumerate(graph_constraints):
                constraint_id, applies_to = _validate_graph_constraint(
                    item,
                    where=f"expected_design_graph.constraints[{index}]",
                    errors=errors,
                )
                if constraint_id is None:
                    continue
                if constraint_id in seen_graph_ids:
                    errors.append(
                        _error(
                            "unknown duplicate",
                            f"expected_design_graph.constraints repeats id {constraint_id}",
                        )
                    )
                seen_graph_ids.add(constraint_id)
                if constraint_id not in normalized_ids:
                    errors.append(
                        _error(
                            "unknown dangling",
                            f"design-graph constraint {constraint_id} is not in expected_normalized",
                        )
                    )
                for node_id in applies_to:
                    if node_id not in node_ids:
                        errors.append(
                            _error(
                                "unknown dangling",
                                f"design-graph constraint {constraint_id} applies_to unknown node {node_id}",
                            )
                        )
    return errors


def load_document(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(_error("unreadable missing_doc", f"{path} is missing")) from exc
    except OSError as exc:
        raise SystemExit(
            _error("unreadable io_error", f"cannot read {path}: {type(exc).__name__}")
        ) from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(
            _error(
                "unreadable json",
                f"invalid JSON in {path} at line {exc.lineno}, column {exc.colno}",
            )
        ) from exc


def catalog_paths(root: Path) -> list[Path]:
    directory = root / FIXTURE_DIR
    if not directory.is_dir():
        raise SystemExit(_error("unreadable missing_doc", f"{directory} is missing"))
    entries = sorted(path for path in directory.iterdir() if path.name and not path.name.startswith("."))
    if not entries:
        raise SystemExit(_error("missing_value catalog", f"{directory} has no fixtures"))
    if len(entries) > MAX_CATALOG_FILES:
        raise SystemExit(
            _error("unknown bound", f"{directory} exceeds {MAX_CATALOG_FILES} files")
        )
    bad = [path.name for path in entries if not _FILENAME_PATTERN.fullmatch(path.name) or not path.is_file()]
    if bad:
        raise SystemExit(
            _error(
                "unknown filename",
                f"{directory} has unknown catalog entries: " + ", ".join(sorted(bad)),
            )
        )
    return entries


def validate_catalog(root: Path) -> list[str]:
    """Validate every committed creator-intent fixture under ``root``."""

    errors: list[str] = []
    seen_ids: set[str] = set()
    for path in catalog_paths(root):
        document = load_document(path)
        fixture_errors = validate_creator_intent_fixture(document)
        prefix = str(FIXTURE_DIR / path.name)
        errors.extend(f"{prefix}: {item}" for item in fixture_errors)
        fixture_id = None
        if isinstance(document, Mapping):
            fixture_id = document.get("fixture_id")
        if fixture_id != path.stem:
            errors.append(
                _error(
                    "unknown fixture_id",
                    f"{prefix} fixture_id must match filename stem {path.stem}",
                )
            )
        if isinstance(fixture_id, str):
            if fixture_id in seen_ids:
                errors.append(
                    _error("unknown duplicate", f"catalog repeats fixture_id {fixture_id}")
                )
            seen_ids.add(fixture_id)
    return errors


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        help="optional fixture JSON; default validates the committed catalog",
    )
    args = parser.parse_args(argv)
    if args.path is None:
        errors = validate_catalog(repo_root())
        label = f"catalog {FIXTURE_DIR}"
    else:
        errors = validate_creator_intent_fixture(load_document(args.path))
        label = str(args.path)
    if errors:
        print("Creator-intent fixture validation failed:", file=sys.stderr)
        for item in errors:
            print(f"  {item}", file=sys.stderr)
        return 1
    print(
        f"Creator-intent fixtures v{SCHEMA_VERSION} accepted {label} "
        f"({TASK_KEY} {CONFLICT_DOMAIN})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
