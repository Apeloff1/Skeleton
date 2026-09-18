from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_retrieval_surface_inventory.py"
SPEC = importlib.util.spec_from_file_location("check_retrieval_surface_inventory", SCRIPT)
assert SPEC and SPEC.loader
policy = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = policy
SPEC.loader.exec_module(policy)

REPO_ROOT = Path(__file__).resolve().parents[1]

CANONICAL_RAG = '''\
class MemoryItem:
    pass

class _FallbackStore:
    def add(self, item):
        return item

    def query(self, embedding, k):
        return []

def _cosine(a, b):
    return 0.0

class RagMemory:
    def remember(self, text, *, metadata=None):
        return MemoryItem()

    def recall(self, query, *, k=5):
        return []
'''

LEGACY_ADAPTER = '''\
class RAGService:
    def store_memory(self, memory_type, content, metadata=None):
        return "id"

    def search_memory(self, query, memory_type=None, limit=5):
        return []

class MockChromaClient:
    def get_or_create_collection(self, name, **kwargs):
        return MockCollection(name)

class MockCollection:
    def add(self, documents, metadatas, ids):
        return None

    def query(self, query_texts, n_results=5, where=None):
        return {"documents": [[]], "ids": [[]]}
'''

OVERLAPPING_STORE = '''\
class InMemoryTFIDFStore:
    def add(self, chunk):
        return None

    def query(self, query_text, *, top_k=5):
        return []

    def _cosine_similarity(self, v1, v2):
        return 0.0
'''

UNRELATED_SAME_BASENAME = '''\
"""shares rag.py basename but is not a retrieval surface."""

def parse_report(path):
    return path

NAME = "rag.py"
'''

BOUNDARIES = """\
| Capability | Canonical owner | Allowed responsibilities | Must not own |
| --- | --- | --- | --- |
| Memory / RAG | `skeleton/jeeves/rag.py` for the current canonical retrieval contract; future generalized retrieval must migrate behind one shared `skeleton/memory/` contract before callers move | document/chunk retrieval, ranking, provenance, storage adapters behind one interface | duplicated vector-store facades |
"""


def _write(root: Path, relative: str, content: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _scan_tree(tmp_path: Path, *, with_docs: bool = True, with_memory: bool = True) -> Path:
    (tmp_path / "skeleton/jeeves").mkdir(parents=True, exist_ok=True)
    if with_memory:
        (tmp_path / "skeleton/memory").mkdir(parents=True, exist_ok=True)
    if with_docs:
        _write(tmp_path, "docs/CANONICAL_MODULE_BOUNDARIES.md", BOUNDARIES)
    return tmp_path


def _family(
    *,
    capability: str = "retrieve",
    function_names: tuple[str, ...] = ("recall", "query"),
    owner_markers: tuple[str, ...] = ("RagMemory",),
    members: tuple[policy.SurfaceMember, ...],
) -> policy.CapabilityFamily:
    return policy.CapabilityFamily(
        capability=capability,
        function_names=function_names,
        owner_markers=owner_markers,
        members=members,
    )


def _closed_kwargs(**overrides):
    kwargs = {
        "documented_owners_file": None,
        "require_documented_owner": False,
        "backend_surfaces": (),
    }
    kwargs.update(overrides)
    return kwargs


def test_repository_retrieval_surface_inventory_is_closed() -> None:
    assert policy.collect_violations(REPO_ROOT, require_roots=True) == []


def test_inventory_table_uses_exclusive_closed_classes() -> None:
    rows = policy.inventory_table(REPO_ROOT)
    assert rows
    classifications = {row["classification"] for row in rows}
    assert classifications <= policy.CLASSIFICATION_SET
    assert "unknown" not in classifications
    capabilities = {str(row["capability"]) for row in rows}
    assert capabilities == set(policy.CAPABILITIES)
    grouped: dict[str, list[str]] = {}
    for row in rows:
        grouped.setdefault(str(row["capability"]), []).append(str(row["classification"]))
        assert row["path"]
        assert row["function_names"] or row["owner_markers"]
        assert row["exists"] is True
    for capability, classes in grouped.items():
        assert classes.count("canonical") == 1, capability
    canonical_retrieve = [
        row
        for row in rows
        if row["capability"] == "retrieve" and row["classification"] == "canonical"
    ]
    assert canonical_retrieve == [
        row for row in canonical_retrieve if row["path"] == "skeleton/jeeves/rag.py"
    ]


def test_canonical_fixture_is_accepted(tmp_path: Path) -> None:
    root = _scan_tree(tmp_path, with_docs=False)
    _write(root, "skeleton/jeeves/rag.py", CANONICAL_RAG)
    inventory = (
        _family(
            members=(policy.SurfaceMember("skeleton/jeeves/rag.py", "canonical"),),
        ),
    )

    assert policy.collect_violations(root, inventory=inventory, **_closed_kwargs()) == []


def test_legacy_adapter_fixture_is_accepted(tmp_path: Path) -> None:
    root = _scan_tree(tmp_path, with_docs=False)
    _write(root, "skeleton/jeeves/rag.py", CANONICAL_RAG)
    _write(root, "backend/services/rag_service.py", LEGACY_ADAPTER)
    inventory = (
        _family(
            function_names=("recall", "search_memory"),
            owner_markers=("RagMemory", "RAGService"),
            members=(
                policy.SurfaceMember("skeleton/jeeves/rag.py", "canonical"),
                policy.SurfaceMember(
                    "backend/services/rag_service.py",
                    "legacy_adapter",
                    notes="leftover chroma adapter",
                ),
            ),
        ),
    )

    errors = policy.collect_violations(
        root,
        inventory=inventory,
        **_closed_kwargs(backend_surfaces=("backend/services/rag_service.py",)),
    )
    assert errors == []


def test_overlapping_fixture_is_accepted(tmp_path: Path) -> None:
    root = _scan_tree(tmp_path, with_docs=False)
    _write(root, "skeleton/jeeves/rag.py", CANONICAL_RAG)
    _write(root, "skeleton/memory/rag.py", OVERLAPPING_STORE)
    inventory = (
        _family(
            function_names=("recall", "query"),
            owner_markers=("RagMemory", "InMemoryTFIDFStore"),
            members=(
                policy.SurfaceMember("skeleton/jeeves/rag.py", "canonical"),
                policy.SurfaceMember("skeleton/memory/rag.py", "overlapping"),
            ),
        ),
    )

    assert policy.collect_violations(root, inventory=inventory, **_closed_kwargs()) == []


def test_unknown_classification_fails_closed(tmp_path: Path) -> None:
    root = _scan_tree(tmp_path, with_docs=False)
    _write(root, "skeleton/jeeves/rag.py", CANONICAL_RAG)
    inventory = (
        _family(members=(policy.SurfaceMember("skeleton/jeeves/rag.py", "unknown"),)),
    )

    errors = policy.collect_violations(root, inventory=inventory, **_closed_kwargs())

    assert any("unknown status fails closed" in item for item in errors)
    assert any("exactly one canonical member required" in item for item in errors)


def test_unlisted_fingerprint_match_is_unknown(tmp_path: Path) -> None:
    root = _scan_tree(tmp_path, with_docs=False)
    _write(root, "skeleton/jeeves/rag.py", CANONICAL_RAG)
    _write(root, "skeleton/memory/extra.py", OVERLAPPING_STORE)
    inventory = (
        _family(
            function_names=("recall", "query"),
            owner_markers=("RagMemory", "InMemoryTFIDFStore"),
            members=(policy.SurfaceMember("skeleton/jeeves/rag.py", "canonical"),),
        ),
    )

    errors = policy.collect_violations(root, inventory=inventory, **_closed_kwargs())

    assert any("unknown retrieval surface: skeleton/memory/extra.py" in item for item in errors)
    assert any("retrieve" in item for item in errors)


def test_fingerprint_match_ignores_basename(tmp_path: Path) -> None:
    root = _scan_tree(tmp_path, with_docs=False)
    canonical = _write(root, "skeleton/jeeves/owner.py", CANONICAL_RAG)
    overlapping = _write(root, "skeleton/memory/also_owner.py", OVERLAPPING_STORE)
    decoy = _write(root, "skeleton/jeeves/rag.py", UNRELATED_SAME_BASENAME)
    family = _family(
        function_names=("recall", "query"),
        owner_markers=("RagMemory", "InMemoryTFIDFStore"),
        members=(
            policy.SurfaceMember("skeleton/jeeves/owner.py", "canonical"),
            policy.SurfaceMember("skeleton/memory/also_owner.py", "overlapping"),
        ),
    )

    canonical_fp = policy.extract_fingerprint(canonical, repo_root=root)
    overlapping_fp = policy.extract_fingerprint(overlapping, repo_root=root)
    decoy_fp = policy.extract_fingerprint(decoy, repo_root=root)

    assert decoy.name == "rag.py"
    assert canonical.name != overlapping.name
    assert policy.file_matches_family(canonical_fp, family)
    assert policy.file_matches_family(overlapping_fp, family)
    assert not policy.file_matches_family(decoy_fp, family)
    assert policy.collect_violations(root, inventory=(family,), **_closed_kwargs()) == []


def test_scan_does_not_leave_allowlisted_roots(tmp_path: Path) -> None:
    root = _scan_tree(tmp_path, with_docs=False)
    _write(root, "skeleton/jeeves/rag.py", CANONICAL_RAG)
    _write(root, "skeleton/kernel/hidden.py", CANONICAL_RAG)
    _write(root, "backend/hidden.py", OVERLAPPING_STORE)
    inventory = (
        _family(members=(policy.SurfaceMember("skeleton/jeeves/rag.py", "canonical"),)),
    )

    assert policy.collect_violations(root, inventory=inventory, **_closed_kwargs()) == []


def test_parse_failure_fails_closed(tmp_path: Path) -> None:
    root = _scan_tree(tmp_path, with_docs=False)
    _write(root, "skeleton/jeeves/rag.py", "def broken(:\n")
    inventory = (
        _family(members=(policy.SurfaceMember("skeleton/jeeves/rag.py", "canonical"),)),
    )

    errors = policy.collect_violations(root, inventory=inventory, **_closed_kwargs())

    assert any("cannot validate Python module: SyntaxError" in item for item in errors)


def test_unreadable_bytes_fail_closed(tmp_path: Path) -> None:
    root = _scan_tree(tmp_path, with_docs=False)
    path = root / "skeleton/jeeves/rag.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\xff\xfe class RagMemory:\n    def recall(self):\n        return []\n")
    inventory = (
        _family(members=(policy.SurfaceMember("skeleton/jeeves/rag.py", "canonical"),)),
    )

    errors = policy.collect_violations(root, inventory=inventory, **_closed_kwargs())

    assert any("cannot validate Python module: UnicodeDecodeError" in item for item in errors)


def test_missing_listed_path_fails_closed(tmp_path: Path) -> None:
    root = _scan_tree(tmp_path, with_docs=False)
    inventory = (
        _family(members=(policy.SurfaceMember("skeleton/jeeves/rag.py", "canonical"),)),
    )

    errors = policy.collect_violations(root, inventory=inventory, **_closed_kwargs())

    assert any("missing listed path skeleton/jeeves/rag.py" in item for item in errors)


def test_listed_path_fingerprint_drift_fails_closed(tmp_path: Path) -> None:
    root = _scan_tree(tmp_path, with_docs=False)
    _write(root, "skeleton/jeeves/rag.py", UNRELATED_SAME_BASENAME)
    inventory = (
        _family(members=(policy.SurfaceMember("skeleton/jeeves/rag.py", "canonical"),)),
    )

    errors = policy.collect_violations(root, inventory=inventory, **_closed_kwargs())

    assert any("does not match declared function/AST fingerprint" in item for item in errors)


def test_missing_scan_root_fails_closed_when_required(tmp_path: Path) -> None:
    _write(tmp_path, "docs/CANONICAL_MODULE_BOUNDARIES.md", BOUNDARIES)
    errors = policy.collect_violations(
        tmp_path,
        inventory=(
            _family(members=(policy.SurfaceMember("skeleton/jeeves/rag.py", "canonical"),)),
        ),
        require_roots=True,
        require_documented_owner=True,
        documented_owners_file="docs/CANONICAL_MODULE_BOUNDARIES.md",
        backend_surfaces=(),
    )

    assert any("missing required scan root: skeleton/jeeves" in item for item in errors)
    assert any("missing documented RAG owner: skeleton/jeeves/rag.py" in item for item in errors)


def test_missing_documented_boundaries_fail_closed(tmp_path: Path) -> None:
    root = _scan_tree(tmp_path, with_docs=False)
    _write(root, "skeleton/jeeves/rag.py", CANONICAL_RAG)
    errors = policy.collect_violations(
        root,
        inventory=(
            _family(members=(policy.SurfaceMember("skeleton/jeeves/rag.py", "canonical"),)),
        ),
        require_roots=True,
        require_documented_owner=True,
        documented_owners_file="docs/CANONICAL_MODULE_BOUNDARIES.md",
        backend_surfaces=(),
    )

    assert any("documented RAG owners file not found" in item for item in errors)


def test_two_canonicals_in_one_capability_fail_closed(tmp_path: Path) -> None:
    root = _scan_tree(tmp_path, with_docs=False)
    _write(root, "skeleton/jeeves/rag.py", CANONICAL_RAG)
    _write(root, "skeleton/memory/rag.py", OVERLAPPING_STORE)
    inventory = (
        _family(
            function_names=("recall", "query"),
            owner_markers=("RagMemory", "InMemoryTFIDFStore"),
            members=(
                policy.SurfaceMember("skeleton/jeeves/rag.py", "canonical"),
                policy.SurfaceMember("skeleton/memory/rag.py", "canonical"),
            ),
        ),
    )

    errors = policy.collect_violations(root, inventory=inventory, **_closed_kwargs())

    assert any("exactly one canonical member required" in item for item in errors)


def test_agent_memory_without_rag_markers_is_not_a_surface(tmp_path: Path) -> None:
    root = _scan_tree(tmp_path, with_docs=False)
    _write(root, "skeleton/jeeves/rag.py", CANONICAL_RAG)
    _write(
        root,
        "skeleton/jeeves/agent/memory.py",
        '''\
class MemoryRetriever:
    def search(self, namespace, query):
        return ()

class MemoryManager:
    def remember(self, namespace, content):
        return None

    def recall(self, namespace, query):
        return ()
''',
    )
    family = _family(
        members=(policy.SurfaceMember("skeleton/jeeves/rag.py", "canonical"),),
    )
    agent_fp = policy.extract_fingerprint(
        root / "skeleton/jeeves/agent/memory.py", repo_root=root
    )

    assert not policy.file_matches_family(agent_fp, family)
    assert policy.collect_violations(root, inventory=(family,), **_closed_kwargs()) == []


def test_documented_owner_must_remain_canonical_for_retrieve() -> None:
    rows = [
        row
        for row in policy.inventory_table(REPO_ROOT)
        if row["path"] == "skeleton/jeeves/rag.py"
    ]
    owned = {str(row["capability"]): str(row["classification"]) for row in rows}
    for capability in policy.DOCUMENTED_CANONICAL_CAPABILITIES:
        assert owned[capability] == "canonical"


def test_checker_does_not_delete_adapters_or_import_skeleton() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "unlink(" not in source
    assert "os.remove" not in source
    assert "Path.unlink" not in source
    assert "never deletes" in source.lower()
    assert "import pydantic" not in source
    assert "import skeleton" not in source
    assert "from skeleton" not in source
    assert "heuristic" in source
