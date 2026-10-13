"""Source-pinned full-app completion census for the existing Jeeves control plane.

This is a non-executing projection of canonical repository authorities.
'Declared', 'implemented', 'tested', and 'release-qualified' are distinct.
No score here asserts that a game, model, adapter or installed app works.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha1, sha256
import json

from .jeeves_appwide_fabric import AppwideInventory, JeevesAppwideError, OPERATIONS, digest

SCHEMA = "skeleton.ai.jeeves_app_completion_census.v1"
SOURCE_MAX_BYTES = 1_000_000
SOURCES = (
    "machine/ai_capabilities.json",
    "machine/ai_app_construction.json",
    "machine/ai_closure_evidence.json",
    "machine/ai_master_plan.json",
    "machine/ai_masterplan_parse_index.json",
    "machine/enterprise_ai_superiority.json",
    "machine/enterprise_system_architecture.json",
    "skeleton/app/manifest.json",
)
KNOWN_CAPABILITY_STATES = frozenset((
    "planned_target", "partial", "present_transport_partial_product",
    "complete",
))


def _json_object(text, name):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise JeevesAppwideError("duplicate JSON key in " + name)
            result[key] = value
        return result

    def reject_nonfinite(value):
        raise JeevesAppwideError("nonfinite JSON in " + name)

    try:
        value = json.loads(text, object_pairs_hook=unique,
                           parse_constant=reject_nonfinite)
    except (ValueError, TypeError, RecursionError) as exc:
        raise JeevesAppwideError("invalid canonical JSON authority: " + name) from exc
    if type(value) is not dict:
        raise JeevesAppwideError("JSON object authority required: " + name)
    return value


def _unique_rows(value, field, source):
    if type(value) is not list or not value:
        raise JeevesAppwideError("missing authority rows: " + source)
    observed = set()
    for row in value:
        if type(row) is not dict or type(row.get(field)) not in (str, int):
            raise JeevesAppwideError("invalid authority row: " + source)
        identifier = row[field]
        if identifier in observed:
            raise JeevesAppwideError("duplicate authority identifier: " + source)
        observed.add(identifier)
    return value


def _states(rows, field):
    return dict(sorted(Counter(row.get(field, "unclassified") for row in rows).items()))


def _exists(inventory, path):
    if type(path) is not str or not path or path.startswith("/") or (
        "\\" in path or any(bit in ("", ".", "..") for bit in path.split("/"))
    ):
        return False
    return path in inventory._files or any(p.startswith(path.rstrip("/") + "/")
                                           for p in inventory._files)


class JeevesCompletionCensus:
    """Never uses the file tree as proof of an operating feature.

    Reports authority-level progress and explicitly missing external
    qualifications. Requires an already scanned AppwideInventory: it does
    not perform model calls, CI calls, scans or mutations on behalf of Jeeves.
    """

    def __init__(self, inventory):
        if not isinstance(inventory, AppwideInventory):
            raise JeevesAppwideError("canonical AppwideInventory required")
        inventory._require_scanned()
        self.inventory = inventory

    def report(self, *, expected_snapshot=None):
        inv = self.inventory
        if expected_snapshot is not None and expected_snapshot != inv._digest:
            raise JeevesAppwideError("stale source inventory snapshot")
        docs = {}
        source_receipts = {}
        for path in SOURCES:
            # The existing inventory reader verifies each path segment and
            # prevents symlink traversal. Only an explicit allowlist is read.
            text = inv._safe_file(path, max_size=SOURCE_MAX_BYTES)
            encoded = text.encode("utf-8")
            docs[path] = _json_object(text, path)
            source_receipts[path] = {
                "sha256": sha256(encoded).hexdigest(),
                "git_blob_sha1": sha1(
                    ("blob " + str(len(encoded)) + "\0").encode("ascii") + encoded
                ).hexdigest(),
                "bytes": len(encoded),
            }

        capabilities = _unique_rows(
            docs[SOURCES[0]].get("capabilities"), "capability_id", SOURCES[0])
        construction = docs[SOURCES[1]]
        planes = _unique_rows(construction.get("planes"), "id", SOURCES[1])
        gaps = _unique_rows(construction.get("gap_register"), "id", SOURCES[1])
        closure = _unique_rows(docs[SOURCES[2]].get("entries"), "gap", SOURCES[2])
        master = _unique_rows(docs[SOURCES[3]].get("volumes"), "key", SOURCES[3])
        index = docs[SOURCES[4]]
        enterprise = docs[SOURCES[5]]
        system = docs[SOURCES[6]]
        app = docs[SOURCES[7]]
        services = _unique_rows(app.get("services"), "name", SOURCES[7])
        domain_rows = _unique_rows(system.get("enterprise_domains"), "id", SOURCES[6])
        workstreams = _unique_rows(system.get("implementation_workstreams"), "id", SOURCES[6])
        journeys = system.get("required_journeys")
        if type(journeys) is not list or not journeys:
            raise JeevesAppwideError("required enterprise journeys missing")
        expected_master_sha = (index.get("sources", {})
                               .get(SOURCES[3], {}).get("git_blob_sha"))
        actual_master_sha = source_receipts[SOURCES[3]]["git_blob_sha1"]
        master_signature_fresh = (
            type(expected_master_sha) is str and expected_master_sha == actual_master_sha
        )

        plane_ids = {p["id"] for p in planes}
        ids = {c["capability_id"] for c in capabilities}
        defects = []
        if len(master) != len({v["id"] for v in master}):
            raise JeevesAppwideError("duplicate masterplan numeric ID")
        for cap in capabilities:
            state = cap.get("implementation_state")
            if state not in KNOWN_CAPABILITY_STATES:
                defects.append({"kind": "unknown_capability_state",
                                "capability": cap["capability_id"]})
            if cap.get("owner_plane") not in plane_ids:
                defects.append({"kind": "undeclared_capability_owner",
                                "capability": cap["capability_id"]})
            missing = sorted(set(cap.get("required_planes", [])) - plane_ids)
            if missing:
                defects.append({"kind": "missing_capability_plane",
                                "capability": cap["capability_id"],
                                "planes": missing})
        # The closure evidence ledger explicitly covers P0; P1 construction
        # gaps are separate, and must not be mislabeled as missing P0 evidence.
        gap_ids = {g["id"] for g in gaps if g.get("priority") == "P0"}
        closure_ids = {e["gap"] for e in closure}
        if gap_ids != closure_ids:
            defects.append({"kind": "construction_closure_ledger_mismatch",
                            "missing_closure": sorted(gap_ids - closure_ids),
                            "unrecognized_closure": sorted(closure_ids - gap_ids)})
        for row in closure:
            matching = next((g for g in gaps if g["id"] == row["gap"]), None)
            if matching and matching.get("status") != row.get("gap_status"):
                defects.append({"kind": "gap_status_disagreement", "gap": row["gap"]})
        if not master_signature_fresh:
            defects.append({"kind": "masterplan_parse_index_source_stale"})

        required = app.get("required_paths")
        if type(required) is not list or any(type(p) is not str for p in required):
            raise JeevesAppwideError("invalid app required-path contract")
        missing_paths = sorted(p for p in required if not _exists(inv, p))
        owner_paths = sorted(set(p.get("owner", "") for p in planes))
        missing_owners = [path for path in owner_paths if not _exists(inv, path)]
        missing_services = [s["name"] for s in services
                            if not _exists(inv, s.get("path"))]

        caps = [{
            "id": c["capability_id"],
            "declared_state": c["implementation_state"],
            "owner": c["owner_plane"], "enabled": c.get("enabled"),
            "readiness_prerequisite_count": len(c.get("readiness_requirements", [])),
            "runtime_qualification_proven": False,
        } for c in capabilities]
        cap_counts = _states(capabilities, "implementation_state")
        volume_counts = _states(master, "implementation_status")
        enterprise_counts = _states(master, "enterprise_grade_state")
        themes = master and docs[SOURCES[3]].get("thematic_parts", [])
        if type(themes) is not list:
            raise JeevesAppwideError("invalid thematic plan groups")
        source_inventory_report = inv.report()
        action_effect_counts = dict(sorted(Counter(
            spec[0] for spec in OPERATIONS.values()).items()))
        closed = sum(g.get("status") == "closed" for g in gaps)
        complete_capabilities = sum(c.get("implementation_state") == "complete"
                                    for c in capabilities)
        enterprise_qualified = sum(
            v.get("enterprise_grade_state") in ("enterprise_qualified", "superior")
            for v in master)

        blockers = []
        if complete_capabilities != len(capabilities):
            blockers.append("product_capability_registry_not_complete")
        if enterprise_qualified != len(master):
            blockers.append("enterprise_volume_qualification_incomplete")
        if any(g.get("status") != "closed" for g in gaps):
            blockers.append("construction_gaps_still_open")
        if defects:
            blockers.append("inconsistent_or_stale_machine_authority")
        if missing_paths or missing_owners or missing_services:
            blockers.append("missing_app_required_paths_or_canonical_owners")
        # A JSON ledger alone cannot establish the live physical target.
        blockers.extend(("exact_head_ci_not_verified_by_this_projection",
                         "assembled_app_device_smoke_not_verified",
                         "trained_model_quality_not_verified",
                         "independent_end_to_end_journeys_not_verified"))
        body = {
            "schema": SCHEMA,
            "inventory_snapshot": inv._digest,
            "source_receipts": source_receipts,
            "reconciled_source_files": len(SOURCES),
            "source_inventory_regular_files": len(inv._files),
            "authority_defects": defects,
            "plan": {
                "volume_total": len(master),
                "volume_implementation_states": volume_counts,
                "volume_enterprise_states": enterprise_counts,
                "enterprise_qualified_volumes": enterprise_qualified,
                "parse_index_masterplan_git_blob_matches": master_signature_fresh,
                "thematic_domain_count": len(themes),
                "thematic_domains": [str(t.get("title", ""))[:120]
                                     for t in themes if type(t) is dict],
                "reported_signed_volumes": index.get("volume_summary", {})
                                           .get("verification_signed"),
                "signed_index_is_not_runtime_acceptance": True,
            },
            "ai_product": {
                "capability_total": len(capabilities),
                "capability_states": cap_counts,
                "registry_complete_count": complete_capabilities,
                "runtime_verified_count": None,
                "capabilities": caps,
            },
            "construction": {
                "plane_total": len(planes),
                "gap_total": len(gaps),
                "p0_evidence_gap_total": len(gap_ids),
                "declared_closed_gaps": closed,
                "closure_ledger_records": len(closure),
                "missing_plane_owners": missing_owners,
            },
            "application": {
                "service_total": len(services),
                "services": [{
                    "name": s["name"], "role": s.get("role"),
                    "declared_path_present": _exists(inv, s.get("path")),
                    "live_service_verified": False
                } for s in services],
                "required_path_total": len(required),
                "missing_required_paths": missing_paths,
                "required_paths_present": len(required) - len(missing_paths),
                "frontend_and_backends_live_verified": False,
            },
            "feature_discovery": {
                "inventory_domain_file_counts": source_inventory_report["domains"],
                "inventory_blocked_path_count": source_inventory_report["skipped_paths"],
                "registered_jeeves_action_count": len(OPERATIONS),
                "registered_action_effects": action_effect_counts,
                "actions": [
                    {"id": name, "effect": values[0],
                     "operator_gate": values[2],
                     "release_verified": False}
                    for name, values in sorted(OPERATIONS.items())
                ],
                "domains_are_overlapping_heuristic_labels": True,
                "adapters_are_not_generic_code_execution": True,
                "inventory_is_only_as_complete_as_selected_checkout": True,
                "whole_app_functional_coverage_percent": None,
            },
            "enterprise": {
                "domain_count": len(domain_rows),
                "domains": [d["id"] for d in domain_rows],
                "workstream_count": len(workstreams),
                "required_journey_count": len(journeys),
                "implementation_state": system.get("completion", {})
                                              .get("implementation_state"),
                "production_qualified": False,
            },
            "readiness": {
                "release_qualified": False,
                "blocking_conditions": blockers,
                "full_app_completion_percent": None,
                "not_claimed": [
                    "file_presence_is_not_functional_feature_coverage",
                    "volume_signoff_is_not_enterprise_qualification",
                    "declared_gap_closure_is_not_installed_release_acceptance",
                    "registered_static_jeeves_actions_do_not_mutate_all_app_features",
                ],
            },
            "read_only": True,
            "model_promotions_performed": False,
            "source_mutations_performed": False,
        }
        return {**body, "digest": digest(body)}
