"""Dependency-reduced recovery bootstrap planning.

Critical recovery must not depend on the same scheduler, queue, telemetry, or
primary service that may be unavailable. This module validates an acyclic
recovery dependency graph, derives deterministic bootstrap/cold-restore order,
and proves that safe-mode nodes remain executable when normal control-plane
services are removed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping


class RecoveryBootstrapError(ValueError):
    """Recovery graph or safe-mode policy is invalid."""


@dataclass(frozen=True, slots=True)
class RecoveryNode:
    name: str
    dependencies: tuple[str, ...] = ()
    safe_mode: bool = False
    cold_restore_order: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name or self.name != self.name.strip():
            raise RecoveryBootstrapError("recovery node name must be normalized")
        if not isinstance(self.dependencies, tuple):
            raise RecoveryBootstrapError("dependencies must be a tuple")
        if len(self.dependencies) != len(set(self.dependencies)):
            raise RecoveryBootstrapError("dependencies contain duplicates")
        if self.name in self.dependencies:
            raise RecoveryBootstrapError("recovery node cannot depend on itself")
        if not isinstance(self.safe_mode, bool):
            raise RecoveryBootstrapError("safe_mode must be boolean")
        if self.cold_restore_order is not None and (
            isinstance(self.cold_restore_order, bool)
            or not isinstance(self.cold_restore_order, int)
            or self.cold_restore_order < 1
        ):
            raise RecoveryBootstrapError(
                "cold_restore_order must be a positive integer"
            )


class RecoveryDependencyGraph:
    """Validated deterministic graph for normal and dependency-reduced recovery."""

    def __init__(self, nodes: Iterable[RecoveryNode]) -> None:
        rows = tuple(nodes)
        if not rows:
            raise RecoveryBootstrapError("recovery graph must be non-empty")
        if any(not isinstance(item, RecoveryNode) for item in rows):
            raise TypeError("nodes must contain RecoveryNode")
        by_name = {item.name: item for item in rows}
        if len(by_name) != len(rows):
            raise RecoveryBootstrapError("recovery node names must be unique")
        for item in rows:
            missing = set(item.dependencies) - set(by_name)
            if missing:
                raise RecoveryBootstrapError(
                    f"{item.name}: unknown dependencies: {sorted(missing)!r}"
                )
        self._nodes = by_name
        # Fail construction on cycles rather than deferring the surprise.
        self.topological_order()

    def node(self, name: str) -> RecoveryNode:
        try:
            return self._nodes[name]
        except KeyError as exc:
            raise RecoveryBootstrapError(f"unknown recovery node: {name}") from exc

    def topological_order(self) -> tuple[str, ...]:
        """Return a deterministic dependency-first order or reject cycles."""

        permanent: set[str] = set()
        temporary: set[str] = set()
        ordered: list[str] = []

        def visit(name: str) -> None:
            if name in permanent:
                return
            if name in temporary:
                raise RecoveryBootstrapError(
                    f"recovery dependency cycle detected at {name}"
                )
            temporary.add(name)
            node = self._nodes[name]
            for dependency in sorted(node.dependencies):
                visit(dependency)
            temporary.remove(name)
            permanent.add(name)
            ordered.append(name)

        for name in sorted(self._nodes):
            visit(name)
        return tuple(ordered)

    def dependency_reduced_order(
        self,
        *,
        unavailable: Iterable[str],
    ) -> tuple[str, ...]:
        """Return safe-mode order after removing unavailable normal services.

        Every selected safe-mode node must have its complete dependency closure
        inside the surviving safe-mode set. A hidden dependency on an
        unavailable or normal-only control plane is a hard failure.
        """

        unavailable_set = frozenset(unavailable)
        unknown = unavailable_set - set(self._nodes)
        if unknown:
            raise RecoveryBootstrapError(
                f"unavailable set contains unknown nodes: {sorted(unknown)!r}"
            )
        survivors = {
            name
            for name, node in self._nodes.items()
            if node.safe_mode and name not in unavailable_set
        }
        if not survivors:
            raise RecoveryBootstrapError("no safe-mode recovery nodes survive")

        for name in sorted(survivors):
            node = self._nodes[name]
            missing = set(node.dependencies) - survivors
            if missing:
                raise RecoveryBootstrapError(
                    f"{name}: safe mode depends on unavailable/non-safe nodes: "
                    f"{sorted(missing)!r}"
                )

        return tuple(
            name
            for name in self.topological_order()
            if name in survivors
        )

    def cold_restore_order(self) -> tuple[str, ...]:
        """Validate and return explicit cold-restore ordering."""

        cold = [node for node in self._nodes.values() if node.cold_restore_order is not None]
        if not cold:
            raise RecoveryBootstrapError("cold restore order is not declared")
        orders = [node.cold_restore_order for node in cold]
        if len(orders) != len(set(orders)):
            raise RecoveryBootstrapError("cold restore order values must be unique")

        ordered = tuple(
            node.name
            for node in sorted(
                cold,
                key=lambda item: (item.cold_restore_order or 0, item.name),
            )
        )
        positions = {name: index for index, name in enumerate(ordered)}
        for name in ordered:
            node = self._nodes[name]
            for dependency in node.dependencies:
                if dependency in positions and positions[dependency] >= positions[name]:
                    raise RecoveryBootstrapError(
                        f"{name}: cold restore dependency order invalid"
                    )
        return ordered

    def describe(self) -> Mapping[str, object]:
        return {
            "nodes": tuple(sorted(self._nodes)),
            "topological_order": self.topological_order(),
            "safe_mode_nodes": tuple(
                sorted(name for name, node in self._nodes.items() if node.safe_mode)
            ),
            "cold_restore_order": self.cold_restore_order(),
        }


DEFAULT_UNAVAILABLE_CONTROL_PLANES = frozenset(
    {"normal_scheduler", "normal_queue", "telemetry"}
)


def build_default_recovery_graph() -> RecoveryDependencyGraph:
    """Canonical dependency-reduced recovery graph for critical bootstrap."""

    return RecoveryDependencyGraph(
        (
            RecoveryNode(
                "local_trust_root",
                safe_mode=True,
                cold_restore_order=1,
            ),
            RecoveryNode(
                "recovery_identity",
                dependencies=("local_trust_root",),
                safe_mode=True,
                cold_restore_order=2,
            ),
            RecoveryNode(
                "cold_authority_store",
                dependencies=("recovery_identity",),
                safe_mode=True,
                cold_restore_order=3,
            ),
            RecoveryNode(
                "repair_executor",
                dependencies=("cold_authority_store",),
                safe_mode=True,
                cold_restore_order=4,
            ),
            RecoveryNode("normal_scheduler"),
            RecoveryNode("normal_queue", dependencies=("normal_scheduler",)),
            RecoveryNode("telemetry"),
            RecoveryNode(
                "normal_runtime",
                dependencies=("normal_queue", "telemetry", "repair_executor"),
            ),
        )
    )


__all__ = [
    "DEFAULT_UNAVAILABLE_CONTROL_PLANES",
    "RecoveryBootstrapError",
    "RecoveryDependencyGraph",
    "RecoveryNode",
    "build_default_recovery_graph",
]
