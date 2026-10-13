"""Bounded measurable full-product acceptance, not plan-signature arithmetic.

The 42-family coverage scope is a *reviewed product taxonomy*, while the
canonical machine authorities enumerate 489 finer obligations as of 2026-10.
Presence of source, a manifest, a workflow, or signed volume is never a
working runtime. Only independent exact-head execution can qualify releases.
No checked-in human/model-produced boolean becomes a release signoff.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
import re

from .jeeves_appwide_fabric import (
    AppwideInventory, JeevesAppwideError, PRIVATE, _relative, digest,
)
from .jeeves_completion_census import (
    JeevesCompletionCensus, _json_object, _unique_rows,
)

SCHEMA = "skeleton.ai.jeeves_measured_product_closure.v1"
SCOPE = "machine/app_completion_scope.json"
GATES = "machine/p1_required_gate_authority.json"
STAGES = (
    "source_owner",
    "implementation_test",
    "runtime_integration",
    "user_journey",
    "release_device",
)
MAX_FAMILIES = 64
MAX_PAGE = 50
MAX_ROOTS = 8
MAX_BYTES = 128_000
FAMILY_ID = re.compile(r"^F[0-9]{2}$")


def _percent(numerator, denominator):
    if type(numerator) is not int or type(denominator) is not int:
        raise JeevesAppwideError("integer metric numerator/denominator required")
    if denominator <= 0 or numerator < 0 or numerator > denominator:
        raise JeevesAppwideError("invalid product measurement denominator")
    return round(100.0 * numerator / denominator, 2)


def _directory_index(inv: AppwideInventory):
    """One O(files*depth) scan; subsequent source scopes query in O(1).

    Only approved, readable original inventory entries count. Files' content
    is *not* read or imported and we never claim that a directory is runnable.
    """
    file_paths = set()
    directories = Counter()
    source_dirs = Counter()
    for path, entry in inv._files.items():
        if not entry.readable or PRIVATE.search(path):
            continue
        file_paths.add(path)
        parts = path.split("/")
        for depth in range(1, len(parts)):
            ancestor = "/".join(parts[:depth])
            directories[ancestor] += 1
            if entry.kind == "source":
                source_dirs[ancestor] += 1
    return file_paths, directories, source_dirs


def _validate_scope(doc):
    if doc.get("schema") != "skeleton.ai.app_completion_scope.v1":
        raise JeevesAppwideError("unknown product acceptance scope schema")
    stages = doc.get("stages")
    if (type(stages) is not list or len(stages) != len(STAGES) or
        tuple(s.get("id") for s in stages if type(s) is dict) != STAGES):
        raise JeevesAppwideError("expected five independent acceptance proof stages")
    if any(type(s.get("source_auto_measure")) is not bool for s in stages):
        raise JeevesAppwideError("typed source-stage measurement policy required")
    if stages[0]["source_auto_measure"] is not True or any(
        row["source_auto_measure"] for row in stages[1:]
    ):
        raise JeevesAppwideError("runtime qualifications cannot be auto-certified")
    policy = doc.get("evidence_policy")
    required_policy = (
        "source_presence_is_not_functionality", "unknown_must_remain_unknown",
        "never_infer_ci_from_workflow_file",
        "never_promote_planned_volume_signatures",
        "independent_evidence_required",
        "regression_invalidates_accepted_receipts",
    )
    if type(policy) is not dict or any(policy.get(k) is not True
                                       for k in required_policy):
        raise JeevesAppwideError("app source proof policy weakened")
    families = doc.get("families")
    if (type(families) is not list or not 1 <= len(families) <= MAX_FAMILIES):
        raise JeevesAppwideError("finite product-family scope required")
    ids = set()
    result = []
    for family in families:
        if type(family) is not dict:
            raise JeevesAppwideError("non-object product family")
        name = family.get("id")
        title = family.get("title")
        owner = family.get("owner")
        domain = family.get("domain")
        roots = family.get("source_roots")
        acceptance = family.get("acceptance_target")
        if (type(name) is not str or not FAMILY_ID.fullmatch(name)
            or name in ids or type(title) is not str or not title.strip()
            or len(title) > 160 or type(domain) is not str
            or not re.fullmatch(r"[a-z][a-z-]{1,31}", domain)
            or type(owner) is not str or not owner
            or type(acceptance) is not str
            or not 12 <= len(acceptance) <= 320
            or family.get("risk_weight") != 1
            or type(family.get("risk_weight")) is not int
            or family.get("required_proof") != list(STAGES)
            or type(roots) is not list
            or not 1 <= len(roots) <= MAX_ROOTS):
            raise JeevesAppwideError("invalid acceptance family record")
        clean_roots = []
        for root in roots:
            try:
                if type(root) is not str:
                    raise JeevesAppwideError("non-string source owner root")
                path = _relative(root)
            except JeevesAppwideError as exc:
                raise JeevesAppwideError("invalid family owner source root") from exc
            if PRIVATE.search(path) or path in clean_roots:
                raise JeevesAppwideError("restricted/duplicate owner scope")
            clean_roots.append(path)
        ids.add(name)
        result.append({**family, "source_roots": clean_roots})
    return sorted(result, key=lambda f: f["id"])


def _family_measure(inv, families):
    file_paths, dirs, source_dirs = _directory_index(inv)
    measured = []
    for family in families:
        roots = family["source_roots"]
        evidence = []
        for root in roots:
            present = root in file_paths or dirs[root] > 0
            source_candidate_count = source_dirs[root]
            if root in file_paths and inv._files[root].kind == "source":
                source_candidate_count += 1
            evidence.append({
                "path": root,
                "present": present,
                "readable_descendant_count": dirs[root] if root not in file_paths
                    else 1,
                "readable_source_candidates": source_candidate_count,
                "owner_functionality_verified": False,
            })
        has_source = any(row["present"] for row in evidence)
        # The source-only stage is a preliminary discovery fact. None of the
        # remaining four acceptance stages are observable from this checkout.
        known = {"source_owner": "located" if has_source else "not_located"}
        known.update({stage: "unverified" for stage in STAGES[1:]})
        measured.append({
            "id": family["id"],
            "title": family["title"],
            "domain": family["domain"],
            "owner": family["owner"],
            "acceptance_target": family["acceptance_target"],
            "root_evidence": evidence,
            "declared_roots": len(roots),
            "located_roots": sum(int(x["present"]) for x in evidence),
            "source_discovered": has_source,
            "source_coverage_is_only_static": True,
            "stage_status": known,
            "independent_stages_verified": 0,
            "independent_stages_unknown": 4,
            "release_qualified": False,
            "eligible_for_automatic_signoff": False,
            "next_required_evidence": [
                "exact-head target tests for " + family["id"],
                "running real backend/frontend/engine integration",
                family["acceptance_target"],
                "installed platform security/recovery/performance proof",
            ],
        })
    return measured


class JeevesMeasuredCompletion:
    """One exact-snapshot baseline, separate evidence/functional denominators."""

    def __init__(self, inventory):
        if not isinstance(inventory, AppwideInventory):
            raise JeevesAppwideError("scanned canonical AppwideInventory required")
        inventory._require_scanned()
        self.inv = inventory

    def _report(self, expected_snapshot=None, expected_scope_sha256=None):
        inv = self.inv
        if expected_snapshot is not None and inv._digest != expected_snapshot:
            raise JeevesAppwideError("stale measurement checkout inventory")
        scope_text = inv._safe_file(SCOPE, max_size=MAX_BYTES)
        scope_sha = sha256(scope_text.encode("utf-8")).hexdigest()
        if (expected_scope_sha256 is not None and
            expected_scope_sha256 != scope_sha):
            raise JeevesAppwideError("source scope changed since accepted measurement")
        scope = _json_object(scope_text, SCOPE)
        families = _validate_scope(scope)
        measured = _family_measure(inv, families)
        census = JeevesCompletionCensus(inv).report(expected_snapshot=expected_snapshot)
        gate_text = inv._safe_file(GATES, max_size=256_000)
        gate_doc = _json_object(gate_text, GATES)
        gates = _unique_rows(gate_doc.get("gates"), "id", GATES)
        if any(row.get("required_for_terminal_p1_promotion") is not True
               for row in gates):
            raise JeevesAppwideError("mandatory release gate marked optional")
        domains = {}
        for domain in sorted({x["domain"] for x in measured}):
            rows = [x for x in measured if x["domain"] == domain]
            domains[domain] = {
                "families": len(rows),
                "source_located": sum(int(x["source_discovered"]) for x in rows),
                "independent_accepted": 0,
                "independent_unknown": 4 * len(rows),
                "release_qualified": 0,
                "source_presence_pct": _percent(sum(int(x["source_discovered"])
                                                    for x in rows), len(rows)),
                "functional_completion_pct": None,
            }
        family_total = len(measured)
        static_count = sum(int(x["source_discovered"]) for x in measured)
        source_roots = sum(x["declared_roots"] for x in measured)
        roots_located = sum(x["located_roots"] for x in measured)
        # 421 volumes + 9 product capabilities + 5 services + 16 workstreams +
        # 12 enterprise journeys + 26 required CI gates in current contracts.
        obligations = {
            "volume_independent_qualification": {
                "total": census["plan"]["volume_total"],
                "registry_enterprise_qualified": census["plan"]["enterprise_qualified_volumes"],
                "independent_runtime_verified": None,
            },
            "product_ai_capabilities": {
                "total": census["ai_product"]["capability_total"],
                "registry_complete": census["ai_product"]["registry_complete_count"],
                "independent_runtime_verified": None,
            },
            "application_services": {
                "total": len(census["application"]["services"]),
                "independently_running": None,
            },
            "enterprise_workstreams": {
                "total": census["enterprise"]["workstream_count"],
                "independently_completed": None,
            },
            "enterprise_journeys": {
                "total": census["enterprise"]["required_journey_count"],
                "independently_completed": None,
            },
            "mandatory_release_gates": {
                "total": len(gates),
                "current_head_successfully_observed": None,
            },
        }
        atomic = sum(entry["total"] for entry in obligations.values())
        defect = census["authority_defects"]
        body = {
            "schema": SCHEMA,
            "inventory_snapshot": inv._digest,
            "scope_sha256": scope_sha,
            "gate_authority_sha256": sha256(gate_text.encode()).hexdigest(),
            "census_digest": census["digest"],
            "family_count": family_total,
            "domain_count": len(domains),
            "family_static_source_located": static_count,
            "family_static_source_unlocated": family_total - static_count,
            "source_presence_percent": _percent(static_count, family_total),
            "owner_root_count": source_roots,
            "owner_root_located": roots_located,
            "owner_root_presence_percent": _percent(roots_located, source_roots),
            "family_independent_acceptance_stage_obligations": 4*family_total,
            "independently_passed_acceptance_stages_observed_here": 0,
            "unknown_independent_acceptance_stages": 4*family_total,
            "release_qualified_families_observed_here": 0,
            "release_qualified_families_unverified": family_total,
            "full_app_completion_percent": None,
            "min_proven_release_completion_percent": 0.0,
            "unknown_or_unqualified_is_not_failed": True,
            "measured_source_pct_is_not_functional_completion": True,
            "individual_capability_coverage_is_not_exhaustive": True,
            "atomic_product_contract_obligations": atomic,
            "atomic_obligation_breakdown": obligations,
            "canonical_authority_defects": defect,
            "domains": domains,
            "family_statuses": measured,
            "source_snapshots_are_not_ci_observations": True,
            "model_quality_not_inferred_from_plan_labels": True,
            "no_tests_or_external_services_invoked": True,
            "no_automatic_model_or_source_changes": True,
        }
        return {**body, "digest": digest(body)}

    def overview(self, *, expected_snapshot=None, expected_scope_sha256=None):
        report = self._report(expected_snapshot, expected_scope_sha256)
        # Only bounded synopsis for model context; family detail is paged.
        return {k: v for k,v in report.items() if k != "family_statuses"}

    def page(self, *, offset=0, limit=12, domain=None, only_missing=False,
             expected_measurement_digest=None, expected_snapshot=None,
             expected_scope_sha256=None):
        if type(offset) is not int or not 0 <= offset <= MAX_FAMILIES:
            raise JeevesAppwideError("bounded family offset required")
        if type(limit) is not int or not 1 <= limit <= MAX_PAGE:
            raise JeevesAppwideError("bounded family page size required")
        if type(only_missing) is not bool:
            raise JeevesAppwideError("boolean static discovery filter required")
        if domain is not None and (
            type(domain) is not str or not 1 <= len(domain) <= 32
        ):
            raise JeevesAppwideError("bounded product family domain required")
        report = self._report(expected_snapshot, expected_scope_sha256)
        if (expected_measurement_digest is not None and
            expected_measurement_digest != report["digest"]):
            raise JeevesAppwideError("stale product evidence measurement receipt")
        rows = report["family_statuses"]
        if domain is not None:
            if domain not in report["domains"]:
                raise JeevesAppwideError("unknown product measurement domain")
            rows = [f for f in rows if f["domain"] == domain]
        if only_missing:
            rows = [f for f in rows if not f["source_discovered"]]
        selected = rows[offset:offset+limit]
        body = {
            "schema": SCHEMA + ".family_page",
            "measurement_digest": report["digest"],
            "source_inventory_snapshot": inv._digest if False else self.inv._digest,
            "scope_sha256": report["scope_sha256"],
            "offset": offset, "limit": limit,
            "domain": domain, "only_missing": only_missing,
            "total_matches": len(rows),
            "next_offset": offset+len(selected)
                if offset+len(selected) < len(rows) else None,
            "families": selected,
            "missing_acceptance_receipts_never_count_as_passes": True,
            "product_release_not_claimed": True,
        }
        return {**body, "digest": digest(body)}
