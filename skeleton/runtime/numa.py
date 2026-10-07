from dataclasses import dataclass


def _nonnegative_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return value


@dataclass(frozen=True)
class NUMANode:
    node_id: int
    cpus: frozenset[int]
    memory: int

    def __post_init__(self) -> None:
        _nonnegative_int(self.node_id, "node_id")
        _nonnegative_int(self.memory, "memory")
        if not isinstance(self.cpus, frozenset):
            raise ValueError("cpus must be a frozenset")
        for cpu in self.cpus:
            _nonnegative_int(cpu, "cpu")


@dataclass(frozen=True)
class NUMAAffinity:
    cpu: int
    preferred_node: int

    def __post_init__(self) -> None:
        _nonnegative_int(self.cpu, "cpu")
        _nonnegative_int(self.preferred_node, "preferred_node")


@dataclass(frozen=True)
class NUMAPlacement:
    node: int | None
    fallback: bool

    def __post_init__(self) -> None:
        if self.node is not None:
            _nonnegative_int(self.node, "node")
        if not isinstance(self.fallback, bool):
            raise ValueError("fallback must be boolean")


def place(nodes, affinity: NUMAAffinity, required_memory: int) -> NUMAPlacement:
    node_items = tuple(nodes)
    if not isinstance(affinity, NUMAAffinity):
        raise ValueError("NUMA affinity required")
    if (
        isinstance(required_memory, bool)
        or not isinstance(required_memory, int)
        or required_memory <= 0
    ):
        raise ValueError("positive required_memory required")

    if any(not isinstance(node, NUMANode) for node in node_items):
        raise ValueError("invalid NUMA topology")
    ids = [node.node_id for node in node_items]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate NUMA node identity")

    cpu_owners: dict[int, int] = {}
    for node in node_items:
        for cpu in node.cpus:
            previous = cpu_owners.setdefault(cpu, node.node_id)
            if previous != node.node_id:
                raise ValueError("CPU belongs to multiple NUMA nodes")

    preferred = next(
        (
            node
            for node in node_items
            if node.node_id == affinity.preferred_node
            and affinity.cpu in node.cpus
            and node.memory >= required_memory
        ),
        None,
    )
    if preferred is not None:
        return NUMAPlacement(preferred.node_id, False)

    candidates = [node for node in node_items if node.memory >= required_memory]
    if not candidates:
        return NUMAPlacement(None, True)

    # Prefer a node that actually owns the requested CPU before falling back to
    # deterministic node identity. This keeps fallback explicit without making
    # an unrelated low-numbered node look local.
    candidates.sort(
        key=lambda node: (
            0 if affinity.cpu in node.cpus else 1,
            0 if node.node_id == affinity.preferred_node else 1,
            node.node_id,
        )
    )
    return NUMAPlacement(candidates[0].node_id, True)
