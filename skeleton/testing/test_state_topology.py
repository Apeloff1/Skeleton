from __future__ import annotations

import json

from scripts.check_state_topology import ROOT, TOPOLOGY_PATH, validate_state_topology


def _topology() -> dict:
    return json.loads((ROOT / TOPOLOGY_PATH).read_text(encoding="utf-8"))


def test_state_topology_is_valid() -> None:
    errors, summary = validate_state_topology(ROOT)

    assert errors == []
    assert summary["ok"] is True
    assert summary["architecture_tag"] == "arch-map/v3.7"
    assert summary["topology_version"] == "1.5.0"
    assert summary["physical_stores"] >= 7
    assert summary["state_domains"] >= 10
    assert summary["state_flows"] >= 7


def test_only_declared_authority_classes_are_sources_of_truth() -> None:
    topology = _topology()
    authoritative = {
        "authoritative",
        "authoritative-unbound",
        "conditional-authoritative",
    }

    for domain in topology["state_domains"]:
        if domain["source_of_truth"]:
            assert domain["authority"] in authoritative, domain["id"]
        else:
            assert domain["authority"] not in authoritative, domain["id"]


def test_derived_and_scratch_state_is_rebuildable() -> None:
    topology = _topology()

    for domain in topology["state_domains"]:
        if domain["authority"] in {"derived", "scratch"}:
            assert domain["rebuildable"] is True, domain["id"]
            assert domain["source_of_truth"] is False, domain["id"]


def test_chroma_is_not_the_target_authority_for_canonical_product_state() -> None:
    topology = _topology()
    chroma_domains = [
        domain
        for domain in topology["state_domains"]
        if domain["physical_store"] in {"backend-data-volume", "chroma-service"}
    ]

    assert chroma_domains
    assert all(domain["source_of_truth"] is False for domain in chroma_domains)
    legacy = next(
        domain
        for domain in chroma_domains
        if domain["id"] == "backend-rag-local-chroma"
    )
    assert legacy["authority"] == "derived"
    assert legacy["rebuildable"] is True
    assert "gap" not in legacy


def test_operation_state_is_production_bound_and_stream_is_non_authoritative() -> None:
    topology = _topology()
    domains = {domain["id"]: domain for domain in topology["state_domains"]}
    stores = {store["id"]: store for store in topology["physical_stores"]}

    operation = domains["canonical-operation-state"]
    stream = domains["operation-event-stream"]

    assert operation["authority"] == "authoritative"
    assert operation["source_of_truth"] is True
    assert operation["physical_store"] == "operation-state-sqlite"
    assert operation["status"] == "production-bound"
    assert operation["rebuildable"] is False
    assert operation["gap"] == "gap-state-authority-convergence"

    assert stream["authority"] == "durable-projection"
    assert stream["source_of_truth"] is False
    assert stream["physical_store"] == "operation-stream-sqlite"
    assert stream["status"] == "production-bound"
    assert stream["derived_from"] == ["canonical-operation-state"]

    for store_id in ("operation-state-sqlite", "operation-stream-sqlite"):
        store = stores[store_id]
        assert store["runtime_service"] == "skeleton"
        assert store["compose_file"] == "docker-compose.yml"
        assert store["volumes"] == ["skeleton_data"]


def test_operation_event_log_does_not_replace_operation_state_contract() -> None:
    topology = _topology()
    flow = next(
        flow
        for flow in topology["state_flows"]
        if flow["id"] == "operation-to-event-stream"
    )

    assert flow["from"] == "canonical-operation-state"
    assert flow["to"] == "operation-event-stream"
    assert "atomic" in flow["rule"] or "reconciliation" in flow["rule"]


def test_recovery_order_restores_authority_before_projections() -> None:
    topology = _topology()
    order = topology["recovery_order"]
    joined = "\n".join(order).lower()

    canonical_index = next(
        i
        for i, step in enumerate(order)
        if "backend-core-app-state" in step
    )
    projection_index = next(
        i
        for i, step in enumerate(order)
        if "rebuild chroma/vector" in step.lower()
    )

    assert canonical_index < projection_index
    assert "authoritative" in joined
    assert "derived" in joined


def test_snapshot_files_are_recovery_aids_not_production_authority() -> None:
    topology = _topology()
    snapshot = next(
        domain
        for domain in topology["state_domains"]
        if domain["id"] == "manual-memory-snapshots"
    )

    assert snapshot["authority"] == "recovery-aid"
    assert snapshot["source_of_truth"] is False
    assert "debug/manual" in snapshot["backup_restore"].lower()

def test_all_state_derivations_resolve_to_real_declared_domains() -> None:
    topology = _topology()
    domains = {
        domain["id"]
        for domain in topology["state_domains"]
    }

    for domain in topology["state_domains"]:
        if domain["id"] == "backend-seeded-content":
            continue
        for source in domain["derived_from"]:
            assert source in domains, (domain["id"], source)


def test_swarm_scratch_and_event_stream_derive_from_canonical_operation_state() -> None:
    topology = _topology()
    domains = {
        domain["id"]: domain
        for domain in topology["state_domains"]
    }

    assert domains["backend-swarm-scratch"]["derived_from"] == [
        "canonical-operation-state"
    ]
    assert domains["operation-event-stream"]["derived_from"] == [
        "canonical-operation-state"
    ]

    flow = next(
        item
        for item in topology["state_flows"]
        if item["id"] == "operation-to-swarm-scratch"
    )
    assert flow["from"] == "canonical-operation-state"
    assert flow["to"] == "backend-swarm-scratch"


def test_functional_ai_memory_authority_is_canonical_and_projections_are_derived() -> None:
    topology = _topology()
    domains = {domain["id"]: domain for domain in topology["state_domains"]}

    canonical = domains["canonical-ai-memory-records"]
    assert canonical["authority"] == "authoritative"
    assert canonical["source_of_truth"] is True
    assert canonical["rebuildable"] is False
    assert canonical["gap"] == "gap-memory-durable-authority"

    for projection_id in ("optional-vector-index", "in-process-retrieval-memory"):
        projection = domains[projection_id]
        assert projection["source_of_truth"] is False
        assert "canonical-ai-memory-records" in projection["derived_from"]


def test_functional_ai_state_domains_are_required_by_construction_closure() -> None:
    topology = _topology()
    construction = json.loads(
        (ROOT / "machine/ai_app_construction.json").read_text(encoding="utf-8")
    )
    domain_ids = {domain["id"] for domain in topology["state_domains"]}

    required = set(construction["functional_ai_closure"]["required_state_domains"])
    assert required
    assert required <= domain_ids


def test_durable_projection_is_non_authoritative_but_not_required_to_be_rebuildable() -> None:
    topology = _topology()
    stream = next(
        domain
        for domain in topology["state_domains"]
        if domain["id"] == "operation-event-stream"
    )

    assert stream["authority"] == "durable-projection"
    assert stream["source_of_truth"] is False
    assert stream["rebuildable"] is False
    assert stream["derived_from"] == ["canonical-operation-state"]
