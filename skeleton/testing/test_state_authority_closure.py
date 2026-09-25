from __future__ import annotations

import copy
import json
from pathlib import Path

from scripts.check_state_authority_closure import (
    compose_closure_errors,
    recovery_drill_errors,
    server_lifecycle_errors,
    topology_closure_errors,
    validate_state_authority_closure,
)


ROOT = Path(__file__).resolve().parents[1]


def _topology() -> dict:
    return json.loads(
        (ROOT / "machine/state_topology.json").read_text(
            encoding="utf-8"
        )
    )


def test_current_repository_state_authority_closure_is_valid() -> None:
    assert validate_state_authority_closure(ROOT) == []


def test_authoritative_unbound_state_is_rejected() -> None:
    topology = copy.deepcopy(_topology())
    domain = next(
        item
        for item in topology["state_domains"]
        if item["id"] == "cognitive-execution-ledger"
    )
    domain["authority"] = "authoritative-unbound"
    domain["status"] = "planned-contract"

    errors = topology_closure_errors(topology)

    assert any(
        "authoritative-unbound domains" in error
        and "cognitive-execution-ledger" in error
        for error in errors
    )


def test_engine_domain_cannot_move_back_to_unbound_store() -> None:
    topology = copy.deepcopy(_topology())
    domain = next(
        item
        for item in topology["state_domains"]
        if item["id"] == "final-ai-result-ledger"
    )
    domain["physical_store"] = "process-memory"

    errors = topology_closure_errors(topology)

    assert (
        "final-ai-result-ledger must bind to engine-execution-sqlite; "
        "found='process-memory'"
    ) in errors


def test_rag_chroma_cannot_be_promoted_to_authority() -> None:
    topology = copy.deepcopy(_topology())
    rag = next(
        item
        for item in topology["state_domains"]
        if item["id"] == "backend-rag-local-chroma"
    )
    rag["authority"] = "authoritative"
    rag["source_of_truth"] = True
    rag["rebuildable"] = False

    errors = topology_closure_errors(topology)

    assert "backend RAG Chroma must be derived" in errors
    assert "backend RAG Chroma cannot be source_of_truth" in errors
    assert "backend RAG Chroma must be rebuildable" in errors


def test_compose_in_memory_engine_state_is_rejected() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    mutated = compose.replace(
        "SKL_ENGINE_EXECUTION_STATE_PATH=/app/data/engine_execution.sqlite",
        "SKL_ENGINE_EXECUTION_STATE_PATH=:memory:",
    )

    errors = compose_closure_errors(mutated)

    assert any(
        "engine_execution.sqlite" in error
        for error in errors
    )
    assert any(
        "in-memory state binding" in error
        for error in errors
    )


def test_server_must_start_operation_outbox_dispatcher() -> None:
    source = (ROOT / "skeleton/api/server.py").read_text(
        encoding="utf-8"
    )
    mutated = source.replace("runtime.start_dispatcher()", "pass")

    errors = server_lifecycle_errors(mutated)

    assert "server does not start operation outbox dispatcher" in errors


def test_server_must_recover_engine_executions_on_startup() -> None:
    source = (ROOT / "skeleton/api/server.py").read_text(
        encoding="utf-8"
    )
    mutated = source.replace(
        "await state.recover_engine_executions()",
        "pass",
    )

    errors = server_lifecycle_errors(mutated)

    assert (
        "server startup does not recover durable engine executions"
        in errors
    )


def test_recovery_drill_must_fence_derived_rebuild() -> None:
    source = (ROOT / "scripts/state_recovery_drill.py").read_text(
        encoding="utf-8"
    )
    mutated = source.replace(
        "derived rebuild forbidden before authoritative verification",
        "derived rebuild may proceed",
    )

    errors = recovery_drill_errors(mutated)

    assert (
        "recovery drill does not fence derived rebuild before verification"
        in errors
    )


def test_recovery_order_requires_verification_before_rebuild() -> None:
    topology = copy.deepcopy(_topology())
    order = topology["recovery_order"]
    verify = next(
        item for item in order
        if "verify authoritative document counts" in item
    )
    rebuild = next(
        item for item in order
        if "rebuild Chroma/vector" in item
    )
    order.remove(verify)
    order.remove(rebuild)
    order.extend([rebuild, verify])

    errors = topology_closure_errors(topology)

    assert (
        "derived rebuild must occur after authoritative restore verification"
        in errors
    )
