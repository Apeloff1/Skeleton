#!/usr/bin/env python3
"""Fail-closed inventory of RAG ingestion/retrieve/rank/provenance/storage surfaces.

Issue #969 Seed 22 (``reserve-S121-retrieval-surface-inventory``) classifies
the retrieval surface by AST function and class names, not filenames.

Every discovered capability surface is classified as exactly one of:

* canonical — the implementation new callers use
* legacy_adapter — a leftover backend/facade adapter (retained, never deleted)
* overlapping — an independent implementation of the same capability
* unknown — discovered and unclassified (always a gate failure)

Matching uses structural fingerprints: defined function/class names plus
RAG-identifying owner markers. Basename equality never classifies a file.
Unknown rows and unreadable modules fail closed. This checker never deletes
adapters and never heuristic-closes a surface.

The walk is bound to ``REQUIRED_SCAN_ROOTS``, ``OPTIONAL_SCAN_ROOTS`` when
present, explicit backend retrieval modules, and RAG owners documented in
``docs/CANONICAL_MODULE_BOUNDARIES.md``. Stdlib only.
"""

from __future__ import annotations

import argparse
import ast
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


TASK_ID = "reserve-S121-retrieval-surface-inventory"
CONFLICT_DOMAIN = "rag.readonly.surface_inventory"
INVENTORY_VERSION = 1

REPO_ROOT = Path(__file__).resolve().parents[1]

REQUIRED_SCAN_ROOTS: tuple[str, ...] = ("skeleton/jeeves",)
OPTIONAL_SCAN_ROOTS: tuple[str, ...] = ("skeleton/memory",)
BACKEND_RETRIEVAL_SURFACES: tuple[str, ...] = (
    "backend/services/rag_service.py",
    "backend/services/agent_knowledge_rag.py",
    "backend/routes/canon_rag.py",
    "backend/knowledge_nexus/engines/aaahrage_hybrid_rag_engine.py",
    "backend/gameforge/exocortex/agentic/hybrid_rag_engine.py",
    "backend/gameforge/rag",
)
DOCUMENTED_OWNERS_FILE = "docs/CANONICAL_MODULE_BOUNDARIES.md"
CANONICAL_RAG_OWNER = "skeleton/jeeves/rag.py"
DOCUMENTED_CANONICAL_CAPABILITIES = ("ingestion", "retrieve", "rank", "storage")

SKIP_PARTS = frozenset(
    {
        "__pycache__",
        ".venv",
        "venv",
        "tests",
        "testing",
        "test",
        "legacy_root",
        "node_modules",
        "satellites",
        "branch-snapshots",
    }
)

CLASSIFICATIONS = ("canonical", "legacy_adapter", "overlapping", "unknown")
CLASSIFICATION_SET = frozenset(CLASSIFICATIONS)
CAPABILITIES = ("ingestion", "retrieve", "rank", "provenance", "storage")
CAPABILITY_SET = frozenset(CAPABILITIES)

_OWNER_ROW_RE = re.compile(
    r"^\|\s*Memory\s*/\s*RAG\s*\|(?P<body>[^\n]*)\|?\s*$",
    re.MULTILINE | re.IGNORECASE,
)
_PATH_RE = re.compile(r"`((?:skeleton|backend)/[^`]+)`")


@dataclass(frozen=True, slots=True)
class SurfaceMember:
    """One classified implementation of a retrieval capability."""

    path: str
    classification: str
    notes: str = ""


@dataclass(frozen=True, slots=True)
class CapabilityFamily:
    """A retrieval capability identified by AST function names, not filenames."""

    capability: str
    function_names: tuple[str, ...]
    owner_markers: tuple[str, ...]
    members: tuple[SurfaceMember, ...]
    notes: str = ""


@dataclass(frozen=True, slots=True)
class ExtractedFingerprint:
    """Structural names taken from one Python module."""

    path: str
    functions: frozenset[str]
    classes: frozenset[str]
    assigns: frozenset[str]
    imports: frozenset[str]
    strings: frozenset[str]
    parse_error: str = ""

    @property
    def definitions(self) -> frozenset[str]:
        return self.functions | self.classes

    @property
    def markers(self) -> frozenset[str]:
        return self.assigns | self.imports | self.strings | self.classes | self.functions


# Explicit table. Discovery of an unlisted file that matches a family
# fingerprint fails closed as unknown. Classification only — do not mutate.
FAMILIES: tuple[CapabilityFamily, ...] = (
    CapabilityFamily(
        capability="ingestion",
        function_names=(
            "remember",
            "ingest",
            "ingest_many",
            "add_document",
            "store_memory",
            "store_learning_session",
            "index_document",
            "add_texts",
            "chunks_from_arts",
            "add",
        ),
        owner_markers=(
            "RagMemory",
            "RAGService",
            "InMemoryTFIDFStore",
            "ChromaDBStore",
            "VectorStore",
            "HybridRAGEngine",
            "AAAHRAGHybridEngine",
            "_FallbackStore",
            "recall_block",
        ),
        members=(
            SurfaceMember(
                path="skeleton/jeeves/rag.py",
                classification="canonical",
                notes="Documented RAG owner; RagMemory.remember is the ingestion path.",
            ),
            SurfaceMember(
                path="skeleton/memory/rag.py",
                classification="overlapping",
                notes="Independent TF-IDF/Chroma add() facade; not yet the shared memory contract.",
            ),
            SurfaceMember(
                path="skeleton/memory/core.py",
                classification="overlapping",
                notes="Monolith InMemoryTFIDFStore.add duplicates memory/rag.py.",
            ),
            SurfaceMember(
                path="skeleton/memory/vector.py",
                classification="overlapping",
                notes="Dense VectorStore.add/add_texts is a second vector-store facade.",
            ),
            SurfaceMember(
                path="backend/services/rag_service.py",
                classification="legacy_adapter",
                notes="Backend Chroma RAGService.store_* leftover parallel to RagMemory.",
            ),
            SurfaceMember(
                path="backend/routes/canon_rag.py",
                classification="legacy_adapter",
                notes="KB artifact chunker (chunks_from_arts) for game-canon retrieval.",
            ),
            SurfaceMember(
                path="backend/knowledge_nexus/engines/aaahrage_hybrid_rag_engine.py",
                classification="overlapping",
                notes="AAAHRAGHybridEngine.index_document is an independent indexer.",
            ),
            SurfaceMember(
                path="backend/gameforge/exocortex/agentic/hybrid_rag_engine.py",
                classification="overlapping",
                notes="HybridRAGEngine.add_document is an independent hybrid ingest path.",
            ),
        ),
        notes="Ingestion into a retrieval store. Canonical owner is skeleton/jeeves/rag.py.",
    ),
    CapabilityFamily(
        capability="retrieve",
        function_names=(
            "recall",
            "retrieve",
            "search_memory",
            "agentic_retrieve",
            "query_unified",
            "search_concepts",
            "build_rag_context",
            "_recall",
            "query",
        ),
        owner_markers=(
            "RagMemory",
            "RAGService",
            "InMemoryTFIDFStore",
            "ChromaDBStore",
            "VectorStore",
            "MemoryTrinity",
            "HybridRAGEngine",
            "AAAHRAGHybridEngine",
            "OmniAdvancedRAGSystem",
            "HybridRAGWiring",
            "recall_block",
            "build_rag_context",
        ),
        members=(
            SurfaceMember(
                path="skeleton/jeeves/rag.py",
                classification="canonical",
                notes="Documented RAG owner; RagMemory.recall is the retrieval path.",
            ),
            SurfaceMember(
                path="skeleton/memory/rag.py",
                classification="overlapping",
                notes="InMemoryTFIDFStore/ChromaDBStore.query is a second retrieval facade.",
            ),
            SurfaceMember(
                path="skeleton/memory/core.py",
                classification="overlapping",
                notes="Monolith TF-IDF query plus MemoryTrinity.query_unified.",
            ),
            SurfaceMember(
                path="skeleton/memory/trinity.py",
                classification="overlapping",
                notes="Split MemoryTrinity.query_unified fuses RAG/CAG/MAG results.",
            ),
            SurfaceMember(
                path="skeleton/memory/vector.py",
                classification="overlapping",
                notes="VectorStore.query is dense retrieval beside the Jeeves owner.",
            ),
            SurfaceMember(
                path="backend/services/rag_service.py",
                classification="legacy_adapter",
                notes="RAGService.search_memory/search_concepts leftover Chroma query API.",
            ),
            SurfaceMember(
                path="backend/services/agent_knowledge_rag.py",
                classification="legacy_adapter",
                notes="build_rag_context Mongo lookup helper named RAG; not the Jeeves contract.",
            ),
            SurfaceMember(
                path="backend/routes/canon_rag.py",
                classification="legacy_adapter",
                notes="Lexical _recall/retrieve/recall_block over Central KB artifacts.",
            ),
            SurfaceMember(
                path="backend/knowledge_nexus/engines/aaahrage_hybrid_rag_engine.py",
                classification="overlapping",
                notes="AAAHRAGHybridEngine.retrieve is an independent hybrid retriever.",
            ),
            SurfaceMember(
                path="backend/gameforge/exocortex/agentic/hybrid_rag_engine.py",
                classification="overlapping",
                notes="HybridRAGEngine.agentic_retrieve is an independent agentic retriever.",
            ),
            SurfaceMember(
                path="backend/gameforge/rag/hybrid_rag_wiring.py",
                classification="legacy_adapter",
                notes="HybridRAGWiring.retrieve is a placeholder vector/graph/keyword adapter.",
            ),
            SurfaceMember(
                path="backend/gameforge/rag/omni_advanced_rag_system.py",
                classification="legacy_adapter",
                notes="OmniAdvancedRAGSystem.retrieve is a simulated multi-facet stub.",
            ),
        ),
        notes="Query/recall against a retrieval store. Canonical owner is skeleton/jeeves/rag.py.",
    ),
    CapabilityFamily(
        capability="rank",
        function_names=(
            "_cosine",
            "_cosine_similarity",
            "_score",
            "_score_document",
            "_merge_and_rerank",
            "_reciprocal_rank_fusion",
        ),
        owner_markers=(
            "RagMemory",
            "InMemoryTFIDFStore",
            "VectorStore",
            "AAAHRAGHybridEngine",
            "HybridRAGWiring",
            "MemoryTrinity",
            "recall_block",
            "_FallbackStore",
        ),
        members=(
            SurfaceMember(
                path="skeleton/jeeves/rag.py",
                classification="canonical",
                notes="Documented RAG owner ranks via _cosine inside _FallbackStore.query.",
            ),
            SurfaceMember(
                path="skeleton/memory/rag.py",
                classification="overlapping",
                notes="Independent TF-IDF _cosine_similarity ranking.",
            ),
            SurfaceMember(
                path="skeleton/memory/core.py",
                classification="overlapping",
                notes="Monolith reciprocal-rank fusion beside the Jeeves cosine ranker.",
            ),
            SurfaceMember(
                path="backend/routes/canon_rag.py",
                classification="legacy_adapter",
                notes="Lexical _score token-overlap ranker for canon chunks.",
            ),
            SurfaceMember(
                path="backend/knowledge_nexus/engines/aaahrage_hybrid_rag_engine.py",
                classification="overlapping",
                notes="AAAHRAG _score_document/_merge_and_rerank is an independent ranker.",
            ),
            SurfaceMember(
                path="backend/gameforge/rag/hybrid_rag_wiring.py",
                classification="legacy_adapter",
                notes="HybridRAGWiring._merge_and_rerank is an empty leftover rank adapter.",
            ),
        ),
        notes="Ranking/reranking of retrieval hits. Canonical owner is skeleton/jeeves/rag.py.",
    ),
    CapabilityFamily(
        capability="provenance",
        function_names=(
            "MemoryTrinity",
            "UnifiedContext",
            "TrinityResult",
            "ScoredChunk",
            "MemoryQueryResult",
        ),
        owner_markers=(
            "MemoryTrinity",
            "UnifiedContext",
            "TrinityResult",
            "ScoredChunk",
            "MemoryQueryResult",
            "provenance_chain",
        ),
        members=(
            SurfaceMember(
                path="skeleton/memory/trinity.py",
                classification="canonical",
                notes="Only in-bound emitter of retrieval provenance_chain; jeeves/rag.py has none.",
            ),
            SurfaceMember(
                path="skeleton/memory/core.py",
                classification="overlapping",
                notes="Monolith TrinityResult/ScoredChunk provenance duplicates trinity.py.",
            ),
            SurfaceMember(
                path="skeleton/memory/types.py",
                classification="overlapping",
                notes="UnifiedContext.provenance_chain schema without an emitter.",
            ),
        ),
        notes=(
            "Retrieval provenance. Documented jeeves/rag.py owner does not implement it; "
            "memory trinity is the in-bound canonical emitter."
        ),
    ),
    CapabilityFamily(
        capability="storage",
        function_names=(
            "_FallbackStore",
            "MemoryStore",
            "VectorStore",
            "InMemoryTFIDFStore",
            "ChromaDBStore",
            "MockChromaClient",
            "MockCollection",
            "HashEmbedder",
        ),
        owner_markers=(
            "_FallbackStore",
            "MemoryStore",
            "VectorStore",
            "InMemoryTFIDFStore",
            "ChromaDBStore",
            "MockChromaClient",
            "MockCollection",
            "HashEmbedder",
        ),
        members=(
            SurfaceMember(
                path="skeleton/jeeves/rag.py",
                classification="canonical",
                notes="Documented RAG owner; _FallbackStore plus optional Chroma collection.",
            ),
            SurfaceMember(
                path="skeleton/memory/store.py",
                classification="overlapping",
                notes="MemoryStore ABC is the future shared contract, not yet the caller owner.",
            ),
            SurfaceMember(
                path="skeleton/memory/rag.py",
                classification="overlapping",
                notes="Duplicated InMemoryTFIDFStore/ChromaDBStore vector-store facade.",
            ),
            SurfaceMember(
                path="skeleton/memory/core.py",
                classification="overlapping",
                notes="Monolith InMemoryTFIDFStore duplicates memory/rag.py storage.",
            ),
            SurfaceMember(
                path="skeleton/memory/vector.py",
                classification="overlapping",
                notes="HashEmbedder/VectorStore is another dense storage facade.",
            ),
            SurfaceMember(
                path="backend/services/rag_service.py",
                classification="legacy_adapter",
                notes="MockChromaClient/MockCollection leftover when Chroma is absent.",
            ),
        ),
        notes="Retrieval storage adapters. Canonical owner is skeleton/jeeves/rag.py.",
    ),
)


def _posix(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def parse_documented_rag_owners(text: str) -> tuple[str, ...]:
    """Extract backtick paths from the Memory / RAG ownership row."""
    match = _OWNER_ROW_RE.search(text)
    if match is None:
        raise ValueError("Memory / RAG ownership row missing from canonical boundaries")
    paths = tuple(dict.fromkeys(_PATH_RE.findall(match.group("body"))))
    if not paths:
        raise ValueError("Memory / RAG ownership row declares no skeleton/ or backend/ paths")
    if CANONICAL_RAG_OWNER not in paths:
        raise ValueError(
            f"Memory / RAG ownership row must declare {CANONICAL_RAG_OWNER}"
        )
    return paths


def load_documented_rag_owners(
    repo_root: Path,
    *,
    documented_owners_file: str = DOCUMENTED_OWNERS_FILE,
) -> tuple[str, ...]:
    path = repo_root / documented_owners_file
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise OSError(f"documented RAG owners file not found: {documented_owners_file}") from exc
    except OSError as exc:
        raise OSError(
            f"documented RAG owners file unreadable: {documented_owners_file}: "
            f"{type(exc).__name__}: {exc}"
        ) from exc
    return parse_documented_rag_owners(text)


def active_scan_prefixes(
    repo_root: Path,
    *,
    required_roots: Sequence[str] = REQUIRED_SCAN_ROOTS,
    optional_roots: Sequence[str] = OPTIONAL_SCAN_ROOTS,
    backend_surfaces: Sequence[str] = BACKEND_RETRIEVAL_SURFACES,
    documented_owners: Sequence[str] = (),
) -> tuple[str, ...]:
    """Return the bound scan prefixes that currently exist (plus required ones)."""
    prefixes: list[str] = list(required_roots)
    for relative in optional_roots:
        if (repo_root / relative).exists():
            prefixes.append(relative)
    prefixes.extend(backend_surfaces)
    for owner in documented_owners:
        if owner not in prefixes:
            prefixes.append(owner)
    return tuple(dict.fromkeys(prefixes))


def _is_under_prefix(relative: str, prefixes: Sequence[str]) -> bool:
    return any(relative == prefix or relative.startswith(prefix + "/") for prefix in prefixes)


def iter_scan_python_files(
    repo_root: Path,
    *,
    prefixes: Sequence[str],
) -> Iterable[Path]:
    """Yield Python files under the declared allowlist only. Never follow symlinks."""
    seen: set[Path] = set()
    for relative_root in prefixes:
        root = repo_root / relative_root
        if root.is_symlink():
            raise OSError(f"scan root must not be a symlink: {relative_root}")
        if root.is_file():
            if not relative_root.endswith(".py"):
                continue
            absolute = root.resolve()
            if absolute in seen:
                continue
            seen.add(absolute)
            yield root
            continue
        if not root.is_dir():
            continue
        stack = [root]
        while stack:
            current = stack.pop()
            child_dirs: list[Path] = []
            python_paths: list[Path] = []
            with os.scandir(current) as entries:
                for entry in sorted(entries, key=lambda item: item.name):
                    if entry.name in SKIP_PARTS:
                        continue
                    if entry.is_symlink():
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        child_dirs.append(Path(entry.path))
                    elif (
                        entry.is_file(follow_symlinks=False)
                        and entry.name.endswith(".py")
                    ):
                        python_paths.append(Path(entry.path))
            for path in python_paths:
                absolute = path.resolve()
                relative = _posix(path, repo_root)
                if not _is_under_prefix(relative, prefixes):
                    continue
                if absolute in seen:
                    continue
                seen.add(absolute)
                yield path
            stack.extend(reversed(child_dirs))


def _assignment_names(node: ast.AST) -> list[str]:
    names: list[str] = []
    if isinstance(node, ast.Name):
        names.append(node.id)
    elif isinstance(node, ast.Tuple):
        for element in node.elts:
            names.extend(_assignment_names(element))
    elif isinstance(node, ast.Starred):
        names.extend(_assignment_names(node.value))
    return names


def extract_fingerprint(path: Path, *, repo_root: Path | None = None) -> ExtractedFingerprint:
    """Parse one module into function names, class names, and AST markers."""
    root = repo_root or REPO_ROOT
    relative = _posix(path, root)
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as exc:
        return ExtractedFingerprint(
            path=relative,
            functions=frozenset(),
            classes=frozenset(),
            assigns=frozenset(),
            imports=frozenset(),
            strings=frozenset(),
            parse_error=f"{type(exc).__name__}: {exc}",
        )
    except UnicodeDecodeError as exc:
        return ExtractedFingerprint(
            path=relative,
            functions=frozenset(),
            classes=frozenset(),
            assigns=frozenset(),
            imports=frozenset(),
            strings=frozenset(),
            parse_error=f"UnicodeDecodeError: {exc}",
        )
    try:
        tree = ast.parse(source, filename=relative)
    except SyntaxError as exc:
        detail = exc.msg or "invalid syntax"
        return ExtractedFingerprint(
            path=relative,
            functions=frozenset(),
            classes=frozenset(),
            assigns=frozenset(),
            imports=frozenset(),
            strings=frozenset(),
            parse_error=f"SyntaxError: {detail}",
        )
    except ValueError as exc:
        return ExtractedFingerprint(
            path=relative,
            functions=frozenset(),
            classes=frozenset(),
            assigns=frozenset(),
            imports=frozenset(),
            strings=frozenset(),
            parse_error=f"{type(exc).__name__}: {exc}",
        )

    functions: set[str] = set()
    classes: set[str] = set()
    assigns: set[str] = set()
    imports: set[str] = set()
    strings: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.add(node.name)
        elif isinstance(node, ast.ClassDef):
            classes.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                assigns.update(_assignment_names(target))
        elif isinstance(node, ast.AnnAssign) and node.target is not None:
            assigns.update(_assignment_names(node.target))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.asname or alias.name.split(".", 1)[0])
                imports.add(alias.name.split(".", 1)[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported = alias.asname or alias.name
                imports.add(imported)
                imports.add(alias.name)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value
            if 0 < len(value) <= 80:
                strings.add(value)

    return ExtractedFingerprint(
        path=relative,
        functions=frozenset(functions),
        classes=frozenset(classes),
        assigns=frozenset(assigns),
        imports=frozenset(imports),
        strings=frozenset(strings),
    )


def file_matches_family(extracted: ExtractedFingerprint, family: CapabilityFamily) -> bool:
    """True when the module implements the family's structural fingerprint.

    Function/class *definitions* supply the behavior names. Owner markers may
    appear as definitions, assignments, imports, or string constants. Basename
    is ignored. Both gates must fire when declared.
    """
    if extracted.parse_error:
        return False
    capability_names = frozenset(family.function_names)
    owner_markers = frozenset(family.owner_markers)
    if not capability_names and not owner_markers:
        return False
    if capability_names and not (capability_names & extracted.definitions):
        return False
    if owner_markers and not (owner_markers & extracted.markers):
        return False
    return True


def _member_map(
    inventory: Sequence[CapabilityFamily],
) -> dict[tuple[str, str], tuple[CapabilityFamily, SurfaceMember]]:
    mapping: dict[tuple[str, str], tuple[CapabilityFamily, SurfaceMember]] = {}
    for family in inventory:
        for member in family.members:
            mapping[(family.capability, member.path)] = (family, member)
    return mapping


def collect_violations(
    repo_root: Path = REPO_ROOT,
    *,
    inventory: Sequence[CapabilityFamily] | None = None,
    require_roots: bool = False,
    required_roots: Sequence[str] = REQUIRED_SCAN_ROOTS,
    optional_roots: Sequence[str] = OPTIONAL_SCAN_ROOTS,
    backend_surfaces: Sequence[str] = BACKEND_RETRIEVAL_SURFACES,
    documented_owners_file: str | None = DOCUMENTED_OWNERS_FILE,
    require_documented_owner: bool = True,
) -> list[str]:
    """Return inventory defects. Unknown and unclassified matches fail closed."""
    families: Sequence[CapabilityFamily] = FAMILIES if inventory is None else inventory
    errors: list[str] = []

    documented_owners: tuple[str, ...] = ()
    if documented_owners_file is not None:
        try:
            documented_owners = load_documented_rag_owners(
                repo_root, documented_owners_file=documented_owners_file
            )
        except (OSError, ValueError) as exc:
            errors.append(str(exc))
            if require_documented_owner:
                return errors

    if require_roots:
        for relative_root in required_roots:
            source_root = repo_root / relative_root
            if not source_root.exists():
                errors.append(f"missing required scan root: {relative_root}")
        if require_documented_owner and not (repo_root / CANONICAL_RAG_OWNER).is_file():
            errors.append(f"missing documented RAG owner: {CANONICAL_RAG_OWNER}")

    prefixes = active_scan_prefixes(
        repo_root,
        required_roots=required_roots,
        optional_roots=optional_roots,
        backend_surfaces=backend_surfaces,
        documented_owners=documented_owners,
    )

    seen_capabilities: set[str] = set()
    seen_pairs: dict[tuple[str, str], str] = {}
    for family in families:
        if family.capability not in CAPABILITY_SET:
            errors.append(f"invalid capability: {family.capability!r}")
        if family.capability in seen_capabilities:
            errors.append(f"capability must be unique: {family.capability}")
        else:
            seen_capabilities.add(family.capability)
        if not family.function_names and not family.owner_markers:
            errors.append(
                f"{family.capability}: fingerprint must declare function names or owner markers"
            )
        canonicals = [member.path for member in family.members if member.classification == "canonical"]
        if len(canonicals) != 1:
            errors.append(
                f"{family.capability}: exactly one canonical member required, found {len(canonicals)}"
            )
        for member in family.members:
            pair = (family.capability, member.path)
            if pair in seen_pairs:
                errors.append(
                    f"path {member.path} is claimed twice under {family.capability}"
                )
            else:
                seen_pairs[pair] = family.capability
            if member.classification not in CLASSIFICATION_SET:
                errors.append(
                    f"{family.capability}: {member.path} has invalid classification "
                    f"{member.classification!r}"
                )
            if member.classification == "unknown":
                errors.append(
                    f"{family.capability}: {member.path} unknown status fails closed"
                )
            if not _is_under_prefix(member.path, prefixes) and (repo_root / member.path).exists():
                errors.append(
                    f"{family.capability}: {member.path} is outside the retrieval scan allowlist"
                )

    if require_documented_owner:
        for capability in DOCUMENTED_CANONICAL_CAPABILITIES:
            family = next((item for item in families if item.capability == capability), None)
            if family is None:
                errors.append(
                    f"documented RAG owner {CANONICAL_RAG_OWNER} missing capability family {capability}"
                )
                continue
            owner_members = [
                member
                for member in family.members
                if member.path == CANONICAL_RAG_OWNER
            ]
            if not owner_members:
                errors.append(
                    f"{capability}: documented RAG owner {CANONICAL_RAG_OWNER} is not inventoried"
                )
            elif owner_members[0].classification != "canonical":
                errors.append(
                    f"{capability}: documented RAG owner {CANONICAL_RAG_OWNER} must be canonical, "
                    f"found {owner_members[0].classification}"
                )

    members = _member_map(families)
    listed_by_path: dict[str, set[str]] = {}
    for family in families:
        for member in family.members:
            listed_by_path.setdefault(member.path, set()).add(family.capability)

    extracted_by_path: dict[str, ExtractedFingerprint] = {}
    try:
        scanned = list(iter_scan_python_files(repo_root, prefixes=prefixes))
    except OSError as exc:
        return [f"scan failed: {type(exc).__name__}: {exc}", *errors]

    for path in scanned:
        relative = _posix(path, repo_root)
        extracted = extract_fingerprint(path, repo_root=repo_root)
        extracted_by_path[relative] = extracted
        if extracted.parse_error:
            errors.append(f"{relative}: cannot validate Python module: {extracted.parse_error}")
            continue
        matches = [family for family in families if file_matches_family(extracted, family)]
        if not matches:
            continue
        listed_capabilities = listed_by_path.get(relative, set())
        for family in matches:
            if family.capability in listed_capabilities:
                continue
            errors.append(
                f"unknown retrieval surface: {relative} matches {family.capability}"
            )

    for (capability, relative), (family, member) in members.items():
        path = repo_root / relative
        if not path.is_file():
            errors.append(f"{capability}: missing listed path {relative}")
            continue
        extracted = extracted_by_path.get(relative)
        if extracted is None:
            extracted = extract_fingerprint(path, repo_root=repo_root)
        if extracted.parse_error:
            message = f"{relative}: cannot validate Python module: {extracted.parse_error}"
            if message not in errors:
                errors.append(message)
            continue
        if not file_matches_family(extracted, family):
            errors.append(
                f"{capability}: {relative} does not match declared function/AST fingerprint"
            )
        if member.classification == "unknown":
            errors.append(f"{relative}: unknown status fails closed")

    return errors


def inventory_table(
    repo_root: Path = REPO_ROOT,
    *,
    inventory: Sequence[CapabilityFamily] | None = None,
) -> list[dict[str, object]]:
    """Return a serializable table of classified retrieval surfaces."""
    families: Sequence[CapabilityFamily] = FAMILIES if inventory is None else inventory
    rows: list[dict[str, object]] = []
    for family in families:
        for member in family.members:
            rows.append(
                {
                    "capability": family.capability,
                    "path": member.path,
                    "classification": member.classification,
                    "function_names": list(family.function_names),
                    "owner_markers": list(family.owner_markers),
                    "notes": member.notes,
                    "exists": (repo_root / member.path).is_file(),
                }
            )
    return rows


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="repository root (defaults to the checkout containing this script)",
    )
    parser.add_argument(
        "--require-roots",
        action="store_true",
        default=True,
        help="fail closed when a required scan root or documented owner is missing (default)",
    )
    parser.add_argument(
        "--allow-missing-roots",
        action="store_false",
        dest="require_roots",
        help="do not require skeleton/jeeves or the documented RAG owner to exist",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve()
    errors = collect_violations(root, require_roots=args.require_roots)
    if errors:
        print("retrieval-surface-inventory: rejected", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    rows = inventory_table(root)
    counts: dict[str, int] = {name: 0 for name in CLASSIFICATIONS}
    capabilities = {str(row["capability"]) for row in rows}
    for row in rows:
        classification = str(row["classification"])
        counts[classification] = counts.get(classification, 0) + 1
    print(
        "retrieval-surface-inventory: OK "
        f"(task={TASK_ID} domain={CONFLICT_DOMAIN} version={INVENTORY_VERSION} "
        f"surfaces={len(rows)} capabilities={','.join(sorted(capabilities))} "
        f"canonical={counts['canonical']} legacy_adapter={counts['legacy_adapter']} "
        f"overlapping={counts['overlapping']} unknown={counts['unknown']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
