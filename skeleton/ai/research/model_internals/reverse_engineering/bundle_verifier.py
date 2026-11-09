"""Cross-report bundle verification for canonical research exports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class BundleItem:
    item_id: str
    kind: str
    digest: str
    dependency_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.item_id or not self.kind:
            raise ReverseEngineeringError("bundle item identity is required")
        if not is_sha256_digest(self.digest):
            raise ReverseEngineeringError("bundle item digest must be sha256 hex")
        if len(self.dependency_ids) != len(set(self.dependency_ids)):
            raise ReverseEngineeringError("bundle dependencies must be unique")
        if self.item_id in self.dependency_ids:
            raise ReverseEngineeringError("bundle item cannot depend on itself")


@dataclass(frozen=True)
class BundleVerificationReport:
    item_count: int
    missing_dependency_count: int
    root_count: int
    leaf_count: int
    cycle_free: bool
    valid: bool
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "item_count": self.item_count,
            "missing_dependency_count": self.missing_dependency_count,
            "root_count": self.root_count,
            "leaf_count": self.leaf_count,
            "cycle_free": self.cycle_free,
            "valid": self.valid,
            "digest": self.digest,
        }


def verify_bundle(
    items: Sequence[BundleItem],
) -> BundleVerificationReport:
    if not items:
        raise ReverseEngineeringError("bundle verification requires items")
    ids = [item.item_id for item in items]
    if len(ids) != len(set(ids)):
        raise ReverseEngineeringError("bundle item ids must be unique")
    by_id = {item.item_id: item for item in items}
    missing = sum(
        dependency not in by_id
        for item in items
        for dependency in item.dependency_ids
    )
    children: dict[str, set[str]] = {item.item_id: set() for item in items}
    for item in items:
        for dependency in item.dependency_ids:
            if dependency in children:
                children[dependency].add(item.item_id)

    state: dict[str, int] = {}
    cycle = False
    def visit(item_id: str) -> None:
        nonlocal cycle
        marker = state.get(item_id, 0)
        if marker == 1:
            cycle = True
            return
        if marker == 2:
            return
        state[item_id] = 1
        for dependency in by_id[item_id].dependency_ids:
            if dependency in by_id:
                visit(dependency)
        state[item_id] = 2

    for item_id in sorted(by_id):
        visit(item_id)
    payload = {
        "items": [
            {
                "item_id": item.item_id,
                "kind": item.kind,
                "digest": item.digest,
                "dependency_ids": list(item.dependency_ids),
            }
            for item in sorted(items, key=lambda value: value.item_id)
        ]
    }
    valid = missing == 0 and not cycle
    return BundleVerificationReport(
        item_count=len(items),
        missing_dependency_count=missing,
        root_count=sum(not item.dependency_ids for item in items),
        leaf_count=sum(not children[item.item_id] for item in items),
        cycle_free=not cycle,
        valid=valid,
        digest=stable_digest(payload),
    )
