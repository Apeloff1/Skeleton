"""Topological build order with strict canonical master-sequence comparison."""
from __future__ import annotations
from collections.abc import Iterable, Mapping
from .canonical import ContractError

WAVE_ORDER = tuple(f"MBW-{idx:02}" for idx in range(8))
DEPENDENCIES = {
    "MBW-00": (),
    "MBW-01": ("MBW-00",),
    "MBW-02": ("MBW-00", "MBW-01"),
    "MBW-03": ("MBW-00", "MBW-01"),
    "MBW-04": ("MBW-02", "MBW-03"),
    "MBW-05": ("MBW-01", "MBW-03", "MBW-04"),
    "MBW-06": ("MBW-02", "MBW-03", "MBW-04"),
    "MBW-07": ("MBW-05", "MBW-06"),
}

def order_waves(requested: Iterable[str], *, dependencies: Mapping[str, Iterable[str]] | None = None) -> tuple[str, ...]:
    graph = DEPENDENCIES if dependencies is None else dependencies
    if len(graph) > 512:
        raise ContractError("dependency graph exceeds bound")
    marked: dict[str, int] = {}
    result: list[str] = []
    def visit(node: str) -> None:
        if node not in graph:
            raise ContractError("unknown build wave")
        if marked.get(node) == 1:
            raise ContractError("cyclic build dependency")
        if marked.get(node) == 2:
            return
        marked[node] = 1
        deps = tuple(graph[node])
        if len(deps) > 128 or len(set(deps)) != len(deps):
            raise ContractError("duplicate or oversized prerequisites")
        for previous in deps:
            visit(previous)
        marked[node] = 2
        result.append(node)
    for current in requested:
        visit(current)
    return tuple(result)

def validate_master_sequence(value: dict) -> None:
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ContractError("unsupported master build schema")
    waves = value.get("waves")
    if not isinstance(waves, list) or len(waves) != 8:
        raise ContractError("eight canonical build waves required")
    observed = {wave.get("id"): wave.get("hard_dependencies") for wave in waves
                if isinstance(wave, dict)}
    if list(observed) != list(WAVE_ORDER):
        raise ContractError("wave build order changed")
    for wave in WAVE_ORDER:
        if tuple(observed[wave]) != DEPENDENCIES[wave]:
            raise ContractError("wave dependency drift: " + wave)
    if order_waves(WAVE_ORDER) != WAVE_ORDER:
        raise ContractError("canonical topology is inconsistent")
