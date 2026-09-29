"""Regression coverage for TREE-016 Frontier runtime extraction."""

from __future__ import annotations

import importlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_frontier_legacy_runtime_modules_reexport_canonical_symbols() -> None:
    checks = (
        ("agent_runtime", "AgentRuntime"),
        ("contracts", "ProvenanceRecord"),
        ("memory", "MemoryItem"),
        ("model_runtime", "ModelRuntime"),
        ("operation_stream", "OperationEventLog"),
        ("operation_stream_store", "SQLiteOperationEventStore"),
        ("resilience", "ResilienceController"),
        ("runtime_events", "execution_result_to_event"),
    )
    for module_name, symbol in checks:
        legacy = importlib.import_module(f"skeleton.frontier.{module_name}")
        canonical = importlib.import_module(
            f"skeleton.frontier.runtime.{module_name}"
        )
        assert getattr(legacy, symbol) is getattr(canonical, symbol)


def test_frontier_public_package_exports_canonical_runtime_symbols() -> None:
    frontier = importlib.import_module("skeleton.frontier")
    agent_runtime = importlib.import_module("skeleton.frontier.runtime.agent_runtime")
    resilience = importlib.import_module("skeleton.frontier.runtime.resilience")

    assert frontier.AgentRuntime is agent_runtime.AgentRuntime
    assert frontier.ExecutionResult is agent_runtime.ExecutionResult
    assert frontier.ResilienceController is resilience.ResilienceController


def test_canonical_runtime_modules_do_not_import_flat_predecessors() -> None:
    runtime_root = ROOT / "skeleton/frontier/runtime"
    forbidden = (
        "skeleton.frontier.agent_runtime",
        "skeleton.frontier.contracts",
        "skeleton.frontier.events",
        "skeleton.frontier.memory",
        "skeleton.frontier.model_runtime",
        "skeleton.frontier.operation_stream",
        "skeleton.frontier.operation_stream_store",
        "skeleton.frontier.retrieval_context",
    )

    for path in runtime_root.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        for import_path in forbidden:
            assert import_path not in source, (path, import_path)
