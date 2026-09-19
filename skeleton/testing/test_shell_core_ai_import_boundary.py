"""Core shell modules must remain import-independent from the AI package."""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from skeleton.shells.ai.distributed_state import (
    DistributedStateConflict as AIDistributedStateConflict,
    InMemoryFencedStore,
    LeaseConflict as AILeaseConflict,
)
from skeleton.shells.distributed_receipts import (
    DistributedReceiptChain,
    HotFloorPosition,
)
from skeleton.shells.receipts import ExecutionReceipt
from skeleton.shells.state_conflicts import (
    DistributedStateConflict,
    LeaseConflict,
)


ROOT = Path(__file__).resolve().parents[1] / "shells"


def _imports(path: Path) -> tuple[str, ...]:
    tree = ast.parse(
        path.read_text(encoding="utf-8"),
        filename=str(path),
    )
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(
                alias.name
                for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom):
            names.append(node.module or "")
    return tuple(names)


def _receipt(name: str) -> ExecutionReceipt:
    return ExecutionReceipt(
        command="python",
        correlation_id=f"corr-{name}",
        fingerprint="a" * 64,
        started_at="2026-09-19T00:00:00+00:00",
        finished_at="2026-09-19T00:00:01+00:00",
        duration_ms=1.0,
        returncode=0,
        ok=True,
        timed_out=False,
        output_limited=False,
        stdout_bytes=1,
        stderr_bytes=0,
        attempt=1,
        receipt_id=f"receipt-{name}",
    )


def test_core_distributed_receipts_has_no_ai_package_import():
    imports = _imports(
        ROOT / "distributed_receipts.py"
    )
    assert not any(
        name == "skeleton.shells.ai"
        or name.startswith(
            "skeleton.shells.ai."
        )
        for name in imports
    )


def test_core_state_conflicts_has_no_ai_package_import():
    imports = _imports(
        ROOT / "state_conflicts.py"
    )
    assert not any(
        name == "skeleton.shells.ai"
        or name.startswith(
            "skeleton.shells.ai."
        )
        for name in imports
    )


def test_core_sequence_index_has_no_ai_package_import():
    imports = _imports(
        ROOT / "sequence_index.py"
    )
    assert not any(
        name == "skeleton.shells.ai"
        or name.startswith(
            "skeleton.shells.ai."
        )
        for name in imports
    )


def test_all_top_level_core_shell_modules_avoid_ai_imports():
    offenders: dict[str, tuple[str, ...]] = {}
    for path in sorted(ROOT.glob("*.py")):
        imports = tuple(
            name
            for name in _imports(path)
            if (
                name == "skeleton.shells.ai"
                or name.startswith(
                    "skeleton.shells.ai."
                )
            )
        )
        if imports:
            offenders[path.name] = imports
    assert offenders == {}


def test_distributed_state_conflict_is_exact_core_reexport():
    assert (
        AIDistributedStateConflict
        is DistributedStateConflict
    )


def test_lease_conflict_is_exact_core_reexport():
    assert AILeaseConflict is LeaseConflict


def test_core_conflict_module_owns_exception_identity():
    assert (
        DistributedStateConflict.__module__
        == "skeleton.shells.state_conflicts"
    )
    assert (
        LeaseConflict.__module__
        == "skeleton.shells.state_conflicts"
    )


def test_core_receipt_chain_module_owns_chain_identity():
    assert (
        DistributedReceiptChain.__module__
        == "skeleton.shells.distributed_receipts"
    )


def test_core_receipt_source_contains_no_lazy_ai_conflict_import():
    text = (
        ROOT / "distributed_receipts.py"
    ).read_text(encoding="utf-8")
    assert "_distributed_state_conflict_type" not in text
    assert (
        "skeleton.shells.ai.distributed_state"
        not in text
    )


def test_local_hot_floor_genesis_is_core_only():
    floor = HotFloorPosition.genesis()
    assert floor.sequence == 0
    assert floor.root_hash == "0" * 64
    assert (
        HotFloorPosition.__module__
        == "skeleton.shells.distributed_receipts"
    )


class StructuralHotFloorStore:
    def __init__(self, position):
        self.value = position
        self.calls: list[str] = []

    def position(self, chain_id: str):
        self.calls.append(chain_id)
        return self.value


def test_receipt_chain_accepts_structural_hot_floor_store():
    store = StructuralHotFloorStore(
        SimpleNamespace(
            sequence=0,
            root_hash="0" * 64,
        )
    )
    chain = DistributedReceiptChain(
        InMemoryFencedStore(),
        hot_floor_store=store,
        hot_floor_chain_id="receipts",
    )
    floor = chain.hot_floor()
    assert floor.sequence == 0
    assert floor.root_hash == "0" * 64
    assert store.calls == ["receipts"]


class MissingPosition:
    pass


def test_receipt_chain_rejects_nonstructural_hot_floor_store():
    with pytest.raises(
        TypeError,
        match="position",
    ):
        DistributedReceiptChain(
            InMemoryFencedStore(),
            hot_floor_store=MissingPosition(),
            hot_floor_chain_id="receipts",
        )


def test_hot_floor_store_and_chain_id_still_pair():
    store = StructuralHotFloorStore(
        SimpleNamespace(
            sequence=0,
            root_hash="0" * 64,
        )
    )
    with pytest.raises(
        ValueError,
        match="configured together",
    ):
        DistributedReceiptChain(
            InMemoryFencedStore(),
            hot_floor_store=store,
        )
    with pytest.raises(
        ValueError,
        match="configured together",
    ):
        DistributedReceiptChain(
            InMemoryFencedStore(),
            hot_floor_chain_id="receipts",
        )


class ConflictOnceStore(InMemoryFencedStore):
    def __init__(self):
        super().__init__()
        self.conflicted = False

    def compare_and_swap(
        self,
        namespace,
        key,
        *,
        expected_revision,
        value,
    ):
        if key == "head" and not self.conflicted:
            self.conflicted = True
            raise DistributedStateConflict(
                "synthetic core conflict"
            )
        return super().compare_and_swap(
            namespace,
            key,
            expected_revision=expected_revision,
            value=value,
        )


def test_core_receipt_chain_catches_core_conflict_identity():
    backend = ConflictOnceStore()
    chain = DistributedReceiptChain(
        backend,
        max_cas_retries=2,
    )
    item = chain.append(
        _receipt("one")
    )
    assert item.sequence == 1
    assert chain.length() == 1
    assert chain.verify()


def test_ai_store_raises_core_conflict_identity():
    backend = InMemoryFencedStore()
    backend.put_if_absent(
        "namespace",
        "key",
        "one",
    )
    with pytest.raises(
        DistributedStateConflict,
    ) as captured:
        backend.put_if_absent(
            "namespace",
            "key",
            "two",
        )
    assert (
        type(captured.value)
        is AIDistributedStateConflict
    )


def test_ai_lease_store_raises_core_lease_identity():
    backend = InMemoryFencedStore(
        clock=lambda: 1.0,
    )
    backend.acquire_lease(
        "namespace",
        "key",
        owner="one",
        ttl_seconds=10.0,
    )
    with pytest.raises(
        LeaseConflict,
    ) as captured:
        backend.acquire_lease(
            "namespace",
            "key",
            owner="two",
            ttl_seconds=10.0,
        )
    assert type(captured.value) is AILeaseConflict


def test_core_conflicts_remain_runtime_errors():
    assert issubclass(
        DistributedStateConflict,
        RuntimeError,
    )
    assert issubclass(
        LeaseConflict,
        RuntimeError,
    )


def test_receipt_chain_source_uses_core_conflict_import():
    text = (
        ROOT / "distributed_receipts.py"
    ).read_text(encoding="utf-8")
    assert (
        "from skeleton.shells.state_conflicts "
        "import DistributedStateConflict"
        in text
    )


def test_ai_distributed_state_reexports_core_conflicts_by_import():
    text = (
        ROOT / "ai" / "distributed_state.py"
    ).read_text(encoding="utf-8")
    assert (
        "from skeleton.shells.state_conflicts import"
        in text
    )
    tree = ast.parse(
        text,
        filename="distributed_state.py",
    )
    local_classes = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
    }
    assert "DistributedStateConflict" not in local_classes
    assert "LeaseConflict" not in local_classes


def test_receipt_chain_does_not_require_ai_type_for_hot_floor():
    class ForeignFloor:
        sequence = 0
        root_hash = "0" * 64

    class ForeignStore:
        def position(self, chain_id):
            assert chain_id == "receipts"
            return ForeignFloor()

    chain = DistributedReceiptChain(
        InMemoryFencedStore(),
        hot_floor_store=ForeignStore(),
        hot_floor_chain_id="receipts",
    )
    assert chain.hot_floor().sequence == 0


def test_core_receipt_import_dependencies_are_small_and_explicit():
    imports = set(
        _imports(
            ROOT / "distributed_receipts.py"
        )
    )
    allowed_prefixes = (
        "__future__",
        "dataclasses",
        "hashlib",
        "typing",
        "skeleton.shells.state_conflicts",
        "skeleton.shells.sequence_index",
        "skeleton.shells.receipts",
    )
    unexpected = tuple(
        sorted(
            name
            for name in imports
            if not any(
                name == prefix
                or name.startswith(
                    prefix + "."
                )
                for prefix in allowed_prefixes
            )
        )
    )
    assert unexpected == ()
