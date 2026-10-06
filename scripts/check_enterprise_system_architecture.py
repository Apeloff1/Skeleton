#!/usr/bin/env python3
"""Fail-closed validation for Skeleton's enterprise system architecture."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = Path("machine/enterprise_system_architecture.json")
ARCHITECTURE_PATH = Path("machine/architecture.json")
CONSTRUCTION_PATH = Path("machine/ai_app_construction.json")
INTERFACES_PATH = Path("machine/capability_interfaces.json")
STATE_TOPOLOGY_PATH = Path("machine/state_topology.json")
RUNTIME_MANIFEST_PATH = Path("skeleton/app/manifest.json")

EXPECTED_SCHEMA = "enterprise-system-architecture/v1"
EXPECTED_STATUS = "active_plan"
EXPECTED_WORKSTREAM_IDS = {f"ENT-{index:02d}" for index in range(1, 17)}
EXPECTED_SERVICE_IDS = {"frontend", "backend", "skeleton", "mongo", "chroma"}
EXPECTED_CORRELATION_KEYS = {
    "trace_id",
    "operation_id",
    "execution_id",
    "tenant_id",
    "release_id",
}
REQUIRED_SOURCE_KEYS = {
    "architecture",
    "architecture_manual",
    "construction",
    "construction_manual",
    "interfaces",
    "state_topology",
    "runtime_manifest",
    "repository_atlas",
    "app_assembly",
    "enterprise_manual",
    "validator",
    "independent_verifier",
    "workflow",
    "tests",
}
REQUIRED_ENTERPRISE_DOMAINS = {
    "product-edge",
    "application-control",
    "ai-execution",
    "canonical-state",
    "retrieval-knowledge",
    "identity-security",
    "reliability-capacity",
    "observability-evaluation",
    "learning-feedback",
    "delivery-release",
    "foundation",
}
REQUIRED_PRODUCTION_EVIDENCE = {
    "production_topology",
    "slo_window",
    "restore_drill",
    "security_evidence",
    "capacity_evidence",
    "golden_journeys",
    "canary_rollback",
    "supply_chain",
    "independent_exact_head_receipt",
}


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _text(value: object, label: str, errors: list[str]) -> str:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{label} must be non-empty text")
        return ""
    return value.strip()


def _string_list(
    value: object,
    *,
    label: str,
    errors: list[str],
    minimum: int = 1,
) -> list[str]:
    if not isinstance(value, list):
        errors.append(f"{label} must be a list")
        return []
    items: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            errors.append(f"{label}[{index}] must be non-empty text")
            continue
        items.append(item.strip())
    if len(items) != len(set(items)):
        errors.append(f"{label} contains duplicates")
    if len(items) < minimum:
        errors.append(f"{label} must contain at least {minimum} items")
    return items


def _object_list(
    value: object,
    *,
    label: str,
    errors: list[str],
    minimum: int = 1,
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        errors.append(f"{label} must be a list")
        return []
    out: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            errors.append(f"{label}[{index}] must be an object")
            continue
        out.append(item)
    if len(out) < minimum:
        errors.append(f"{label} must contain at least {minimum} objects")
    return out


def _unique_ids(
    objects: list[dict[str, Any]],
    *,
    label: str,
    errors: list[str],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(objects):
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id:
            errors.append(f"{label}[{index}].id must be non-empty")
            continue
        if item_id in result:
            errors.append(f"{label} contains duplicate id {item_id}")
        result[item_id] = item
    return result


def _cycle_nodes(
    graph: dict[str, set[str]],
) -> set[str]:
    temporary: set[str] = set()
    permanent: set[str] = set()
    cycles: set[str] = set()

    def visit(node: str) -> None:
        if node in permanent:
            return
        if node in temporary:
            cycles.add(node)
            return
        temporary.add(node)
        for dependency in graph.get(node, set()):
            if dependency in temporary:
                cycles.update({node, dependency})
            else:
                visit(dependency)
        temporary.remove(node)
        permanent.add(node)

    for node in graph:
        visit(node)
    return cycles


def validate_payloads(
    contract: dict[str, Any],
    architecture: dict[str, Any],
    construction: dict[str, Any],
    interfaces: dict[str, Any],
    state_topology: dict[str, Any],
    runtime_manifest: dict[str, Any],
    *,
    repo_root: Path = ROOT,
) -> list[str]:
    errors: list[str] = []

    if contract.get("schema_version") != EXPECTED_SCHEMA:
        errors.append("enterprise schema_version drifted")
    if contract.get("status") != EXPECTED_STATUS:
        errors.append("enterprise status must remain active_plan before runtime signoff")
    if contract.get("plan_complete") is not True:
        errors.append("enterprise architecture plan must declare plan_complete=true")
    if not isinstance(contract.get("production_claim"), bool):
        errors.append("production_claim must be boolean")

    sources = contract.get("sources")
    if not isinstance(sources, dict):
        errors.append("enterprise sources must be an object")
        sources = {}
    if set(sources) != REQUIRED_SOURCE_KEYS:
        errors.append("enterprise source keys drifted")
    for key, raw in sorted(sources.items()):
        if not isinstance(raw, str) or not raw:
            errors.append(f"enterprise source {key} must be a path")
            continue
        path = repo_root / raw
        if not path.is_file():
            errors.append(f"enterprise source path missing: {key}: {raw}")

    compatibility = contract.get("compatibility")
    if not isinstance(compatibility, dict):
        errors.append("enterprise compatibility must be an object")
        compatibility = {}
    if compatibility.get("required_architecture_tag") != architecture.get(
        "architecture_tag"
    ):
        errors.append("enterprise architecture tag does not match machine architecture")
    if compatibility.get("required_construction_version") != construction.get(
        "construction_version"
    ):
        errors.append("enterprise construction version does not match AI construction")
    expected_plane_count = compatibility.get("required_capability_plane_count")
    planes = _object_list(
        construction.get("planes"),
        label="construction.planes",
        errors=errors,
        minimum=1,
    )
    plane_map = _unique_ids(planes, label="construction.planes", errors=errors)
    if expected_plane_count != len(plane_map):
        errors.append(
            "enterprise required_capability_plane_count does not match construction planes"
        )

    entries = _object_list(
        interfaces.get("entries"),
        label="interfaces.entries",
        errors=errors,
        minimum=1,
    )
    minimum_interfaces = compatibility.get("required_interface_minimum")
    if (
        isinstance(minimum_interfaces, bool)
        or not isinstance(minimum_interfaces, int)
        or minimum_interfaces < 1
    ):
        errors.append("required_interface_minimum must be a positive integer")
    elif len(entries) < minimum_interfaces:
        errors.append("capability interface registry is below enterprise minimum")

    manifest_services = _object_list(
        runtime_manifest.get("services"),
        label="runtime_manifest.services",
        errors=errors,
        minimum=1,
    )
    manifest_names = {
        str(service.get("name"))
        for service in manifest_services
        if isinstance(service.get("name"), str)
    }
    required_services = set(
        _string_list(
            compatibility.get("required_runtime_services"),
            label="compatibility.required_runtime_services",
            errors=errors,
            minimum=1,
        )
    )
    if required_services != EXPECTED_SERVICE_IDS:
        errors.append("enterprise required runtime service set drifted")
    if manifest_names != required_services:
        errors.append("runtime manifest services do not match enterprise contract")

    runtime_cell = contract.get("runtime_cell")
    if not isinstance(runtime_cell, dict):
        errors.append("runtime_cell must be an object")
        runtime_cell = {}
    cell_services = _object_list(
        runtime_cell.get("services"),
        label="runtime_cell.services",
        errors=errors,
        minimum=1,
    )
    cell_map = _unique_ids(cell_services, label="runtime_cell.services", errors=errors)
    if set(cell_map) != manifest_names:
        errors.append("runtime cell service set must exactly match runtime manifest")
    for service_id, service in cell_map.items():
        manifest = next(
            (item for item in manifest_services if item.get("name") == service_id),
            None,
        )
        if manifest is None:
            continue
        depends_on = set(
            _string_list(
                service.get("depends_on", []),
                label=f"runtime_cell.services[{service_id}].depends_on",
                errors=errors,
                minimum=0,
            )
        )
        manifest_deps = set(manifest.get("depends_on") or [])
        if depends_on != manifest_deps:
            errors.append(
                f"runtime cell dependency drift for {service_id}: "
                f"{sorted(depends_on)} != {sorted(manifest_deps)}"
            )
        minimum_replicas = service.get("minimum_production_replicas")
        if (
            isinstance(minimum_replicas, bool)
            or not isinstance(minimum_replicas, int)
            or minimum_replicas < 0
        ):
            errors.append(
                f"runtime cell {service_id} minimum_production_replicas invalid"
            )
        if service_id in {"frontend", "backend", "skeleton"} and (
            not isinstance(minimum_replicas, int) or minimum_replicas < 2
        ):
            errors.append(f"production serving tier {service_id} must be redundant")
        if service_id == "mongo" and (
            not isinstance(minimum_replicas, int) or minimum_replicas < 3
        ):
            errors.append("production mongo target must be replicated")

    domains = _object_list(
        contract.get("enterprise_domains"),
        label="enterprise_domains",
        errors=errors,
        minimum=len(REQUIRED_ENTERPRISE_DOMAINS),
    )
    domain_map = _unique_ids(domains, label="enterprise_domains", errors=errors)
    if set(domain_map) != REQUIRED_ENTERPRISE_DOMAINS:
        errors.append("enterprise domain set drifted")
    mapped_planes: list[str] = []
    for domain_id, domain in domain_map.items():
        mapped_planes.extend(
            _string_list(
                domain.get("planes"),
                label=f"enterprise_domains[{domain_id}].planes",
                errors=errors,
                minimum=1,
            )
        )
        _string_list(
            domain.get("owns"),
            label=f"enterprise_domains[{domain_id}].owns",
            errors=errors,
            minimum=1,
        )
        _string_list(
            domain.get("must_not_own"),
            label=f"enterprise_domains[{domain_id}].must_not_own",
            errors=errors,
            minimum=1,
        )
    if len(mapped_planes) != len(set(mapped_planes)):
        errors.append("AI capability plane is mapped to multiple enterprise domains")
    if set(mapped_planes) != set(plane_map):
        errors.append("enterprise domains do not map every construction plane exactly once")

    deployment_profiles = _object_list(
        contract.get("deployment_profiles"),
        label="deployment_profiles",
        errors=errors,
        minimum=4,
    )
    profiles = _unique_ids(
        deployment_profiles,
        label="deployment_profiles",
        errors=errors,
    )
    production = profiles.get("production-ha")
    if production is None:
        errors.append("production-ha deployment profile is required")
    else:
        if production.get("production_eligible") is not True:
            errors.append("production-ha must be production eligible")
        _string_list(
            production.get("requirements"),
            label="production-ha.requirements",
            errors=errors,
            minimum=8,
        )

    tenancy = contract.get("tenancy")
    if not isinstance(tenancy, dict):
        errors.append("tenancy must be an object")
        tenancy = {}
    _string_list(
        tenancy.get("identity_keys"),
        label="tenancy.identity_keys",
        errors=errors,
        minimum=3,
    )
    _string_list(
        tenancy.get("isolation_requirements"),
        label="tenancy.isolation_requirements",
        errors=errors,
        minimum=6,
    )
    privileged = tenancy.get("privileged_access")
    if not isinstance(privileged, dict) or set(privileged) != {
        "production_admin",
        "break_glass",
        "service_accounts",
    }:
        errors.append("tenancy privileged_access contract is incomplete")

    governance = contract.get("data_governance")
    if not isinstance(governance, dict):
        errors.append("data_governance must be an object")
        governance = {}
    if set(
        _string_list(
            governance.get("classes"),
            label="data_governance.classes",
            errors=errors,
            minimum=4,
        )
    ) != {"public", "internal", "confidential", "restricted"}:
        errors.append("enterprise data classes drifted")
    canonical_vs_derived = governance.get("canonical_vs_derived")
    if not isinstance(canonical_vs_derived, dict):
        errors.append("canonical_vs_derived must be an object")
    else:
        for key in ("canonical", "derived", "scratch"):
            _string_list(
                canonical_vs_derived.get(key),
                label=f"canonical_vs_derived.{key}",
                errors=errors,
                minimum=3,
            )

    security = contract.get("security_architecture")
    if not isinstance(security, dict):
        errors.append("security_architecture must be an object")
        security = {}
    _string_list(
        security.get("control_families"),
        label="security_architecture.control_families",
        errors=errors,
        minimum=10,
    )
    crypto = security.get("cryptography")
    if not isinstance(crypto, dict) or set(crypto) != {
        "in_transit",
        "at_rest",
        "key_management",
    }:
        errors.append("security cryptography baseline is incomplete")
    vulnerability = security.get("vulnerability_response")
    if not isinstance(vulnerability, dict) or not {
        "critical",
        "high",
        "medium",
        "low",
        "rule",
    } <= set(vulnerability):
        errors.append("vulnerability response policy is incomplete")

    reliability = contract.get("reliability")
    if not isinstance(reliability, dict):
        errors.append("reliability must be an object")
        reliability = {}
    _string_list(
        reliability.get("failure_domains"),
        label="reliability.failure_domains",
        errors=errors,
        minimum=10,
    )
    _string_list(
        reliability.get("patterns"),
        label="reliability.patterns",
        errors=errors,
        minimum=10,
    )

    slos = contract.get("service_level_objectives")
    if not isinstance(slos, dict):
        errors.append("service_level_objectives must be an object")
        slos = {}
    if slos.get("status") != "targets-not-claims":
        errors.append("SLO status must remain targets-not-claims before production evidence")
    slo_objects = _object_list(
        slos.get("objectives"),
        label="service_level_objectives.objectives",
        errors=errors,
        minimum=8,
    )
    _unique_ids(slo_objects, label="service_level_objectives.objectives", errors=errors)
    for index, slo in enumerate(slo_objects):
        _text(slo.get("target"), f"SLO[{index}].target", errors)
        _text(slo.get("scope"), f"SLO[{index}].scope", errors)

    dr = contract.get("disaster_recovery")
    if not isinstance(dr, dict):
        errors.append("disaster_recovery must be an object")
        dr = {}
    dr_tiers = _object_list(
        dr.get("tiers"),
        label="disaster_recovery.tiers",
        errors=errors,
        minimum=3,
    )
    if len(dr_tiers) != 3:
        errors.append("enterprise DR must define exactly three recovery tiers")
    for index, tier in enumerate(dr_tiers):
        _text(tier.get("class"), f"DR[{index}].class", errors)
        _text(tier.get("rpo"), f"DR[{index}].rpo", errors)
        _text(tier.get("rto"), f"DR[{index}].rto", errors)
        _string_list(
            tier.get("examples"),
            label=f"DR[{index}].examples",
            errors=errors,
            minimum=2,
        )
    _string_list(
        dr.get("backup_requirements"),
        label="disaster_recovery.backup_requirements",
        errors=errors,
        minimum=5,
    )
    _string_list(
        dr.get("restore_order"),
        label="disaster_recovery.restore_order",
        errors=errors,
        minimum=5,
    )

    capacity = contract.get("capacity_and_fairness")
    if not isinstance(capacity, dict):
        errors.append("capacity_and_fairness must be an object")
        capacity = {}
    _string_list(
        capacity.get("controls"),
        label="capacity_and_fairness.controls",
        errors=errors,
        minimum=8,
    )
    _string_list(
        capacity.get("overload_order"),
        label="capacity_and_fairness.overload_order",
        errors=errors,
        minimum=5,
    )

    observability = contract.get("observability_and_sre")
    if not isinstance(observability, dict):
        errors.append("observability_and_sre must be an object")
        observability = {}
    correlation_keys = set(
        _string_list(
            observability.get("correlation_keys"),
            label="observability_and_sre.correlation_keys",
            errors=errors,
            minimum=5,
        )
    )
    if correlation_keys != EXPECTED_CORRELATION_KEYS:
        errors.append("enterprise correlation key set drifted")
    _string_list(
        observability.get("telemetry"),
        label="observability_and_sre.telemetry",
        errors=errors,
        minimum=8,
    )
    incident = observability.get("incident_management")
    if not isinstance(incident, dict):
        errors.append("incident_management must be an object")
    else:
        _string_list(
            incident.get("severity"),
            label="incident_management.severity",
            errors=errors,
            minimum=4,
        )
        _string_list(
            incident.get("requirements"),
            label="incident_management.requirements",
            errors=errors,
            minimum=5,
        )

    change = contract.get("change_and_release")
    if not isinstance(change, dict):
        errors.append("change_and_release must be an object")
        change = {}
    _string_list(
        change.get("principles"),
        label="change_and_release.principles",
        errors=errors,
        minimum=5,
    )
    _string_list(
        change.get("promotion_evidence"),
        label="change_and_release.promotion_evidence",
        errors=errors,
        minimum=10,
    )

    operating = contract.get("operating_model")
    if not isinstance(operating, dict):
        errors.append("operating_model must be an object")
        operating = {}
    _object_list(
        operating.get("roles"),
        label="operating_model.roles",
        errors=errors,
        minimum=6,
    )
    _string_list(
        operating.get("minimum_runbooks"),
        label="operating_model.minimum_runbooks",
        errors=errors,
        minimum=10,
    )
    cadence = operating.get("review_cadence")
    if not isinstance(cadence, dict) or not {
        "daily",
        "weekly",
        "monthly",
        "quarterly",
        "annual",
    } <= set(cadence):
        errors.append("enterprise operating review cadence is incomplete")

    _string_list(
        contract.get("required_journeys"),
        label="required_journeys",
        errors=errors,
        minimum=12,
    )

    workstreams = _object_list(
        contract.get("implementation_workstreams"),
        label="implementation_workstreams",
        errors=errors,
        minimum=16,
    )
    workstream_map = _unique_ids(
        workstreams,
        label="implementation_workstreams",
        errors=errors,
    )
    if set(workstream_map) != EXPECTED_WORKSTREAM_IDS:
        errors.append("enterprise implementation workstream set drifted")
    graph: dict[str, set[str]] = {}
    for workstream_id, workstream in workstream_map.items():
        dependencies = set(
            _string_list(
                workstream.get("depends_on", []),
                label=f"implementation_workstreams[{workstream_id}].depends_on",
                errors=errors,
                minimum=0,
            )
        )
        unknown = dependencies - set(workstream_map)
        if unknown:
            errors.append(
                f"workstream {workstream_id} has unknown dependencies: {sorted(unknown)}"
            )
        graph[workstream_id] = dependencies
        priority = workstream.get("priority")
        if priority not in {"P0", "P1", "P2"}:
            errors.append(f"workstream {workstream_id} priority is invalid")
        _string_list(
            workstream.get("exit"),
            label=f"implementation_workstreams[{workstream_id}].exit",
            errors=errors,
            minimum=2,
        )
    cycles = _cycle_nodes(graph)
    if cycles:
        errors.append(
            "enterprise implementation workstream DAG contains cycle: "
            + ", ".join(sorted(cycles))
        )
    if "ENT-16" in graph and len(graph["ENT-16"]) < 4:
        errors.append("ENT-16 production acceptance must depend on major closure work")

    evidence_model = contract.get("evidence_model")
    if not isinstance(evidence_model, dict):
        errors.append("evidence_model must be an object")
        evidence_model = {}
    _string_list(
        evidence_model.get("architecture_plan_complete_requires"),
        label="evidence_model.architecture_plan_complete_requires",
        errors=errors,
        minimum=5,
    )
    _string_list(
        evidence_model.get("production_ready_requires"),
        label="evidence_model.production_ready_requires",
        errors=errors,
        minimum=8,
    )
    _text(evidence_model.get("signoff_rule"), "evidence_model.signoff_rule", errors)

    completion = contract.get("completion")
    if not isinstance(completion, dict):
        errors.append("completion must be an object")
        completion = {}
    if completion.get("architecture_plan_state") != "complete_candidate":
        errors.append("architecture plan state must be complete_candidate")
    _string_list(
        completion.get("signable_now"),
        label="completion.signable_now",
        errors=errors,
        minimum=10,
    )
    _string_list(
        completion.get("not_signable_without_runtime_evidence"),
        label="completion.not_signable_without_runtime_evidence",
        errors=errors,
        minimum=5,
    )

    evidence_files = _string_list(
        contract.get("evidence_files"),
        label="evidence_files",
        errors=errors,
        minimum=10,
    )
    for raw in evidence_files:
        if not (repo_root / raw).is_file():
            errors.append(f"enterprise evidence file missing: {raw}")

    if contract.get("production_claim") is True:
        if completion.get("implementation_state") != "evidenced":
            errors.append(
                "production_claim=true requires completion.implementation_state=evidenced"
            )
        production_evidence = contract.get("production_evidence")
        if not isinstance(production_evidence, dict):
            errors.append("production_claim=true requires production_evidence object")
        else:
            missing_evidence = sorted(
                REQUIRED_PRODUCTION_EVIDENCE - set(production_evidence)
            )
            if missing_evidence:
                errors.append(
                    "production evidence incomplete: " + ", ".join(missing_evidence)
                )
            for key in REQUIRED_PRODUCTION_EVIDENCE:
                value = production_evidence.get(key)
                if not isinstance(value, str) or not value.strip():
                    errors.append(f"production evidence {key} must be non-empty")

    # Cross-check that the state topology still shares the active architecture tag.
    if state_topology.get("architecture_tag") != architecture.get("architecture_tag"):
        errors.append("state topology architecture tag drifted")

    return errors


def validate(repo_root: Path = ROOT) -> list[str]:
    try:
        contract = _load_json(repo_root / CONTRACT_PATH)
        architecture = _load_json(repo_root / ARCHITECTURE_PATH)
        construction = _load_json(repo_root / CONSTRUCTION_PATH)
        interfaces = _load_json(repo_root / INTERFACES_PATH)
        state_topology = _load_json(repo_root / STATE_TOPOLOGY_PATH)
        runtime_manifest = _load_json(repo_root / RUNTIME_MANIFEST_PATH)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        return [f"cannot load enterprise architecture sources: {exc}"]

    return validate_payloads(
        contract,
        architecture,
        construction,
        interfaces,
        state_topology,
        runtime_manifest,
        repo_root=repo_root,
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evidence(head_sha: str, repo_root: Path = ROOT) -> dict[str, Any]:
    errors = validate(repo_root)
    contract = _load_json(repo_root / CONTRACT_PATH)
    evidence_files = contract.get("evidence_files") or []
    digests = {
        str(raw): _sha256(repo_root / str(raw))
        for raw in sorted(evidence_files)
        if isinstance(raw, str) and (repo_root / raw).is_file()
    }
    payload: dict[str, Any] = {
        "schema_version": EXPECTED_SCHEMA,
        "verifier": "enterprise-system-architecture-structural-v1",
        "head_sha": str(head_sha).strip(),
        "valid": not errors,
        "errors": errors,
        "contract_digest": _sha256(repo_root / CONTRACT_PATH),
        "file_digests": digests,
        "architecture_tag": contract.get("compatibility", {}).get(
            "required_architecture_tag"
        ),
        "construction_version": contract.get("compatibility", {}).get(
            "required_construction_version"
        ),
        "plan_complete": contract.get("plan_complete"),
        "production_claim": contract.get("production_claim"),
    }
    payload["evidence_digest"] = hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--head-sha", default="")
    parser.add_argument("--evidence-out")
    parser.add_argument("--print-evidence", action="store_true")
    args = parser.parse_args(argv)

    if args.head_sha:
        result = evidence(args.head_sha)
        if args.evidence_out:
            Path(args.evidence_out).write_text(
                json.dumps(result, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        if args.print_evidence or args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["valid"] else 1

    errors = validate()
    if args.json:
        print(
            json.dumps(
                {
                    "schema_version": EXPECTED_SCHEMA,
                    "valid": not errors,
                    "errors": errors,
                },
                indent=2,
                sort_keys=True,
            )
        )
    elif errors:
        print("enterprise-system-architecture: rejected")
        for error in errors:
            print("  -", error)
    else:
        print(
            "enterprise-system-architecture: OK "
            "(plan_complete=true; production_claim=false)"
        )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
