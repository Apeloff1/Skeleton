"""Strict, offline, non-executing source qualification for Jeeves Git patches.

This analyzer is a *post-generation* boundary. A local GGUF's Python/JSON/
TOML suggestions are not executable merely because they look plausible.
The checker parses supported source formats, binds every finding to the
exact reviewed replacement SHA-256 and reports unsupported formats as
UNVERIFIED rather than fabricating a pass.

It does NOT import/compile/execute generated modules, run shell or Node,
resolve third-party dependencies, test runtime semantics, change project
files, grant agent tools, or claim release/hardware correctness.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import PurePosixPath
import time
import tomllib

from .desktop_patch_bundle import PatchEntry, PortablePatchPlan

SCHEMA = "jeeves.workspace.static-source-qualification.v1"
MAX_ANALYSIS_SOURCE_BYTES = 768 * 1024
MAX_AST_NODES_PER_FILE = 50000
MAX_PYTHON_DEFINITIONS = 4096
MAX_WALL_SECONDS = 10

SUPPORTED = frozenset((".py", ".pyi", ".json", ".toml"))
UNVERIFIED = frozenset((
    ".md", ".rst", ".txt", ".yaml", ".yml",
    ".js", ".jsx", ".ts", ".tsx", ".css", ".html", ".sql",
    ".go", ".rs", ".java", ".kt", ".swift", ".c", ".h",
    ".cpp", ".hpp", ".rb", ".sh", ".ps1", ".xml", ".ini", ".cfg",
))


class StaticSourceHold(ValueError):
    """An exact source patch fails the finite, non-executing parser checks."""


@dataclass(frozen=True, slots=True)
class SyntaxIssue:
    code: str
    relative_path: str
    replacement_sha256: str
    line: int | None
    column: int | None

    def __post_init__(self):
        if self.code not in (
            "python-syntax", "python-recursion", "python-ast-size",
            "python-source", "json-syntax", "json-duplicate-key",
            "json-nonfinite", "json-recursion", "toml-syntax",
            "parser-budget-exhausted",
        ):
            raise StaticSourceHold("unrecognized static diagnostic")
        if (
            type(self.relative_path) is not str
            or not self.relative_path
            or type(self.replacement_sha256) is not str
            or len(self.replacement_sha256) != 64
        ):
            raise StaticSourceHold("finding is not bound to original source identity")
        for name in ("line", "column"):
            value = getattr(self, name)
            if value is not None and (
                type(value) is not int or not 1 <= value <= 1000000
            ):
                raise StaticSourceHold("untrusted line/column diagnostic")

    def to_public(self) -> dict[str, object]:
        # Never expose a SyntaxError.msg: it can embed private source text.
        return {
            "code": self.code,
            "path": self.relative_path,
            "replacement_sha256": self.replacement_sha256,
            "line": self.line,
            "column": self.column,
            "source_text_disclosed": False,
        }


@dataclass(frozen=True, slots=True)
class FileQualification:
    path: str
    replacement_sha256: str
    language: str
    status: str
    bytes_checked: int
    parser_fingerprint: str | None
    syntax_nodes: int | None
    top_level_definitions: tuple[str, ...]
    import_count: int
    issues: tuple[SyntaxIssue, ...]

    def __post_init__(self):
        if (
            type(self.path) is not str or not self.path
            or type(self.replacement_sha256) is not str
            or len(self.replacement_sha256) != 64
            or self.language not in (
                "python", "json", "toml", "unverified-format",
            )
            or self.status not in (
                "parse-clean", "syntax-held", "unverified",
            )
            or type(self.bytes_checked) is not int
            or not 1 <= self.bytes_checked <= MAX_ANALYSIS_SOURCE_BYTES
            or type(self.import_count) is not int or self.import_count < 0
            or type(self.top_level_definitions) is not tuple
            or type(self.issues) is not tuple
        ):
            raise StaticSourceHold("malformed bounded original source qualification")
        if self.status == "syntax-held" and not self.issues:
            raise StaticSourceHold("source was rejected without a finite diagnostic")
        if self.status != "syntax-held" and self.issues:
            raise StaticSourceHold("source parser diagnostic was suppressed")
        if self.status != "parse-clean" and self.parser_fingerprint is not None:
            raise StaticSourceHold("unsupported/error source cannot claim parsed AST")
        if self.parser_fingerprint is not None and (
            len(self.parser_fingerprint) != 64
            or any(x not in "0123456789abcdef" for x in self.parser_fingerprint)
        ):
            raise StaticSourceHold("invalid parser fingerprint")
        if self.syntax_nodes is not None and (
            type(self.syntax_nodes) is not int or self.syntax_nodes < 0
        ):
            raise StaticSourceHold("invalid AST node count")

    def to_public(self) -> dict[str, object]:
        return {
            "path": self.path,
            "replacement_sha256": self.replacement_sha256,
            "language": self.language,
            "status": self.status,
            "bytes_checked": self.bytes_checked,
            "parser_fingerprint": self.parser_fingerprint,
            "syntax_nodes": self.syntax_nodes,
            # Symbols can be sensitive source metadata, so public receipt
            # only reports the count. Full names remain in the typed review.
            "top_level_definition_count": len(self.top_level_definitions),
            "import_count": self.import_count,
            "issues": [x.to_public() for x in self.issues],
            "executed_source_code": False,
        }


@dataclass(frozen=True, slots=True)
class SourceQualification:
    source_manifest_sha256: str
    source_patch_sha256: str
    files: tuple[FileQualification, ...]
    total_bytes: int
    status: str

    def __post_init__(self):
        for digest in (self.source_manifest_sha256, self.source_patch_sha256):
            if (
                type(digest) is not str or len(digest) != 64
                or any(ch not in "0123456789abcdef" for ch in digest)
            ):
                raise StaticSourceHold("unbound source review qualification digest")
        if (
            type(self.files) is not tuple
            or not 1 <= len(self.files) <= 24
            or any(type(x) is not FileQualification for x in self.files)
            or type(self.total_bytes) is not int
            or self.total_bytes != sum(x.bytes_checked for x in self.files)
            or not 1 <= self.total_bytes <= MAX_ANALYSIS_SOURCE_BYTES
            or self.status not in ("parse-clean", "mixed-unverified", "syntax-held")
        ):
            raise StaticSourceHold("invalid typed original source qualification")
        expected = (
            "syntax-held"
            if any(f.status == "syntax-held" for f in self.files)
            else (
                "mixed-unverified"
                if any(f.status == "unverified" for f in self.files)
                else "parse-clean"
            )
        )
        if expected != self.status:
            raise StaticSourceHold("unsupported format or syntax issue wrongly certified")

    @property
    def permits_inert_export(self) -> bool:
        return self.status != "syntax-held"

    def to_public(self) -> dict[str, object]:
        return {
            "schema": SCHEMA,
            "source_manifest_sha256": self.source_manifest_sha256,
            "source_patch_sha256": self.source_patch_sha256,
            "file_count": len(self.files),
            "total_bytes": self.total_bytes,
            "status": self.status,
            "parse_clean_count": sum(f.status == "parse-clean" for f in self.files),
            "unverified_count": sum(f.status == "unverified" for f in self.files),
            "syntax_held_count": sum(f.status == "syntax-held" for f in self.files),
            "files": [f.to_public() for f in self.files],
            "inert_patch_export_eligible": self.permits_inert_export,
            "all_languages_parsed": all(f.status == "parse-clean" for f in self.files),
            "runtime_tests_executed": False,
            "source_code_executed": False,
            "model_executed_from_patch": False,
            "native_device_qualified": False,
            "release_certified": False,
        }


def _issue(entry: PatchEntry, kind: str, line=None, column=None) -> SyntaxIssue:
    def bounded(n):
        return n if type(n) is int and 1 <= n <= 1000000 else None
    return SyntaxIssue(
        code=kind, relative_path=entry.path,
        replacement_sha256=entry.replacement_sha256,
        line=bounded(line), column=bounded(column),
    )


def _file(
    entry: PatchEntry, *, language: str, status: str,
    fingerprint=None, nodes=None, definitions=(), imports=0, issues=(),
) -> FileQualification:
    return FileQualification(
        path=entry.path,
        replacement_sha256=entry.replacement_sha256,
        language=language, status=status,
        bytes_checked=entry.replacement_bytes,
        parser_fingerprint=fingerprint, syntax_nodes=nodes,
        top_level_definitions=tuple(definitions),
        import_count=imports,
        issues=tuple(issues),
    )


def _python(entry: PatchEntry) -> FileQualification:
    try:
        tree = ast.parse(
            entry.replacement_text, filename="<private-original-source>",
            mode="exec", type_comments=True,
        )
        count = 0
        imports = 0
        for node in ast.walk(tree):
            count += 1
            if count > MAX_AST_NODES_PER_FILE:
                return _file(
                    entry, language="python", status="syntax-held",
                    issues=(_issue(entry, "python-ast-size"),),
                )
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                imports += 1
        definitions = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                definitions.append(node.name)
                if len(definitions) > MAX_PYTHON_DEFINITIONS:
                    return _file(
                        entry, language="python", status="syntax-held",
                        issues=(_issue(entry, "python-ast-size"),),
                    )
        # A canonical structural digest is a parser-version-dependent
        # diagnostic. The original source byte digest is independently
        # authoritative and appears in every file receipt.
        fingerprint = sha256(
            ast.dump(tree, annotate_fields=True, include_attributes=False)
            .encode("utf-8", "strict"),
        ).hexdigest()
        return _file(
            entry, language="python", status="parse-clean",
            fingerprint=fingerprint, nodes=count,
            definitions=definitions, imports=imports,
        )
    except SyntaxError as exc:
        return _file(
            entry, language="python", status="syntax-held",
            issues=(_issue(entry, "python-syntax", exc.lineno, exc.offset),),
        )
    except RecursionError:
        return _file(
            entry, language="python", status="syntax-held",
            issues=(_issue(entry, "python-recursion"),),
        )
    except (MemoryError, ValueError, UnicodeError):
        return _file(
            entry, language="python", status="syntax-held",
            issues=(_issue(entry, "python-source"),),
        )


def _reject_duplicate_keys(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise _DuplicateJSONKey
        result[name] = value
    return result


class _DuplicateJSONKey(ValueError):
    """Strict original source JSON must not conceal duplicate definitions."""


def _reject_nonfinite(_value):
    raise _NonfiniteJSON


class _NonfiniteJSON(ValueError):
    """Nonfinite values are not valid portable original JSON."""


def _json(entry: PatchEntry) -> FileQualification:
    try:
        parsed = json.loads(
            entry.replacement_text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite,
        )
        # Parsing only: do not emit private contents or pretend the schema
        # is correct without its actual application-level validation.
        fingerprint = sha256(
            json.dumps(
                parsed, ensure_ascii=False, sort_keys=True,
                allow_nan=False, separators=(",", ":"),
            ).encode("utf-8", "strict"),
        ).hexdigest()
        return _file(
            entry, language="json", status="parse-clean",
            fingerprint=fingerprint,
        )
    except json.JSONDecodeError as exc:
        return _file(
            entry, language="json", status="syntax-held",
            issues=(_issue(entry, "json-syntax", exc.lineno, exc.colno),),
        )
    except _DuplicateJSONKey:
        return _file(
            entry, language="json", status="syntax-held",
            issues=(_issue(entry, "json-duplicate-key"),),
        )
    except _NonfiniteJSON:
        return _file(
            entry, language="json", status="syntax-held",
            issues=(_issue(entry, "json-nonfinite"),),
        )
    except (RecursionError, MemoryError, ValueError, UnicodeError):
        return _file(
            entry, language="json", status="syntax-held",
            issues=(_issue(entry, "json-recursion"),),
        )


def _toml(entry: PatchEntry) -> FileQualification:
    try:
        parsed = tomllib.loads(entry.replacement_text)
        if type(parsed) is not dict:
            raise ValueError("invalid TOML object")
        fingerprint = sha256(
            entry.replacement_text.encode("utf-8", "strict"),
        ).hexdigest()
        return _file(
            entry, language="toml", status="parse-clean",
            fingerprint=fingerprint,
        )
    except (tomllib.TOMLDecodeError, UnicodeError, ValueError, RecursionError, MemoryError) as exc:
        return _file(
            entry, language="toml", status="syntax-held",
            issues=(_issue(
                entry, "toml-syntax",
                getattr(exc, "lineno", None),
                getattr(exc, "colno", None),
            ),),
        )


def qualify_source_file(entry: PatchEntry) -> FileQualification:
    """Check exact replacement bytes, never open or execute a source path."""
    if type(entry) is not PatchEntry:
        raise StaticSourceHold("typed original source plan entry required")
    entry.__post_init__()
    extension = PurePosixPath(entry.path).suffix.lower()
    if extension in (".py", ".pyi"):
        return _python(entry)
    if extension == ".json":
        return _json(entry)
    if extension == ".toml":
        return _toml(entry)
    if extension not in UNVERIFIED:
        raise StaticSourceHold("unsupported source format cannot become parse-clean")
    return _file(
        entry, language="unverified-format", status="unverified",
    )


def qualify_patch_sources(plan: PortablePatchPlan) -> SourceQualification:
    """Bind independent parser results to one complete source patch digest."""
    if type(plan) is not PortablePatchPlan:
        raise StaticSourceHold("reviewed typed patch must exist first")
    plan.__post_init__()
    selected = plan.entries
    total = sum(item.replacement_bytes for item in selected)
    if total > MAX_ANALYSIS_SOURCE_BYTES:
        raise StaticSourceHold("source corpus exceeds bounded parse budget")
    results = []
    started = time.monotonic()
    for item in selected:
        if time.monotonic() - started > MAX_WALL_SECONDS:
            results.append(_file(
                item, language=(
                    "python" if item.path.endswith((".py", ".pyi"))
                    else "unverified-format"
                ),
                status="syntax-held",
                issues=(_issue(item, "parser-budget-exhausted"),),
            ))
            # Remaining proposed files must not be reported as parsed;
            # no export can proceed with an incomplete source admission.
            for remaining in selected[len(results):]:
                results.append(_file(
                    remaining, language="unverified-format",
                    status="syntax-held",
                    issues=(_issue(remaining, "parser-budget-exhausted"),),
                ))
            break
        results.append(qualify_source_file(item))
    status = (
        "syntax-held" if any(f.status == "syntax-held" for f in results)
        else "mixed-unverified"
        if any(f.status == "unverified" for f in results)
        else "parse-clean"
    )
    return SourceQualification(
        source_manifest_sha256=plan.manifest_sha256,
        source_patch_sha256=plan.patch_sha256,
        files=tuple(results), total_bytes=total, status=status,
    )


def require_parseable_patch(plan: PortablePatchPlan) -> SourceQualification:
    """Fail closed for malformed *supported* source, not unverified formats."""
    report = qualify_patch_sources(plan)
    if (
        not report.permits_inert_export
        or report.source_manifest_sha256 != plan.manifest_sha256
        or report.source_patch_sha256 != plan.patch_sha256
    ):
        raise StaticSourceHold(
            "original generated source contains structural errors; fix and re-review",
        )
    # The standard Python parser accepts some imports which can never
    # resolve from the proposed package hierarchy (e.g. three parent
    # levels from a top-level module). Block only these proven invalid
    # relations; external/unchanged project modules remain unverified.
    from .desktop_source_graph import (
        SourceGraphHold, analyze_python_source_graph,
    )
    try:
        graph = analyze_python_source_graph(plan)
    except SourceGraphHold as exc:
        raise StaticSourceHold(
            "original Python dependency graph cannot be qualified",
        ) from exc
    if not graph.permits_inert_export:
        raise StaticSourceHold(
            "generated source has invalid Python relative import or unbounded graph",
        )
    return report


__all__ = [
    "SCHEMA", "SUPPORTED", "UNVERIFIED",
    "StaticSourceHold", "SyntaxIssue", "FileQualification",
    "SourceQualification", "qualify_source_file", "qualify_patch_sources",
    "require_parseable_patch",
]
