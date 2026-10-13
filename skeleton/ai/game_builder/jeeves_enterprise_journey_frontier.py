"""Source-bound enterprise end-to-end journey verification frontier.

This is the *missing release layer* above unit-test linkage. The 12 canonical
enterprise user journeys and 84 independent acceptance obligations are
immutable contracts, not evidence of running or passing them. Neither a test
file nor a masterplan signoff can turn a journey green.
"""
from __future__ import annotations

import ast
from hashlib import sha256
import re

from .jeeves_appwide_fabric import AppwideInventory, JeevesAppwideError, digest
from .jeeves_completion_census import _json_object

SCHEMA="skeleton.ai.enterprise_journey_release_frontier.v1"
CONTRACT="machine/app_release_journey_contract.json"
ENTERPRISE="machine/enterprise_system_architecture.json"
SCOPE="machine/app_completion_scope.json"
GATES="machine/p1_required_gate_authority.json"
CAPABILITIES="machine/ai_capabilities.json"
MAX_SOURCE_BYTES=256_000
MAX_TEST_BYTES=160_000
MAX_PAGE=12
AXES=(
    "real_executable_target",
    "user_outcome",
    "durable_state",
    "negative_and_security_path",
    "restart_or_failure_recovery",
    "observability_and_trace",
    "device_and_release_qualification",
)
POLICIES=(
    "canonical_journey_denominator_frozen",
    "no_source_file_proves_runtime_execution",
    "no_test_candidate_counts_as_pass",
    "release_requires_independent_operator_evidence",
    "failed_skipped_cancelled_queued_are_not_success",
    "all_requirement_axes_mandatory",
    "default_all_states_unknown",
    "never_automatically_signoff",
)
TEST_PATH=re.compile(r"^tests/test_[a-z0-9_]+\.py$")
JOURNEY_IDS=tuple(f"J{i:02d}" for i in range(1,13))
FAMILY_IDS=frozenset(f"F{i:02d}" for i in range(1,43))


def _test_case_count(text: str, path: str):
    """Static declarations only; no dynamic imports or subprocess execution."""
    try:
        tree=ast.parse(text,filename=path)
    except (SyntaxError,RecursionError,ValueError) as exc:
        raise JeevesAppwideError("malformed source-linked enterprise test") from exc
    names=[]
    for node in tree.body:
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name.startswith("test_"):
            names.append(node.name)
        if isinstance(node,ast.ClassDef):
            for method in node.body:
                if isinstance(method,(ast.FunctionDef,ast.AsyncFunctionDef)) and method.name.startswith("test_"):
                    names.append(node.name+"."+method.name)
    if len(set(names))!=len(names) or not names:
        raise JeevesAppwideError("empty or duplicate enterprise candidate tests: "+path)
    return len(names)


class JeevesEnterpriseJourneyFrontier:
    """Fixed 12-journey/84-axis release gap report bound to exact source hashes."""

    def __init__(self,inventory: AppwideInventory):
        if not isinstance(inventory,AppwideInventory):
            raise JeevesAppwideError("scanned source inventory required")
        inventory._require_scanned()
        self.inv=inventory

    def _build(self,*,expected_snapshot=None,expected_contract_sha256=None):
        inv=self.inv
        if expected_snapshot is not None and expected_snapshot!=inv._digest:
            raise JeevesAppwideError("stale journey inventory source cursor")
        sources={}
        docs={}
        for path in (CONTRACT,ENTERPRISE,SCOPE,GATES,CAPABILITIES):
            source=inv._safe_file(path,max_size=MAX_SOURCE_BYTES)
            sources[path]=sha256(source.encode("utf-8")).hexdigest()
            docs[path]=_json_object(source,path)
        if (expected_contract_sha256 is not None and
            expected_contract_sha256!=sources[CONTRACT]):
            raise JeevesAppwideError("journey release source contract changed")
        contract=docs[CONTRACT]
        enterprise=docs[ENTERPRISE]
        policy=contract.get("policy")
        if (contract.get("schema")!="skeleton.ai.enterprise_journey_acceptance.v1"
            or contract.get("source_authority")!=ENTERPRISE
            or contract.get("scope_authority")!=SCOPE
            or type(policy) is not dict or
            any(policy.get(k) is not True for k in POLICIES) or
            contract.get("required_acceptance_axes")!=list(AXES)):
            raise JeevesAppwideError("enterprise journey acceptance policy mismatch")
        families=docs[SCOPE].get("families")
        if (type(families) is not list or len(families)!=42
            or any(type(f) is not dict or type(f.get("id")) is not str
                   for f in families)
            or {f["id"] for f in families}!=FAMILY_IDS):
            raise JeevesAppwideError("fixed 42 product source families changed")
        required=enterprise.get("required_journeys")
        if (type(required) is not list or len(required)!=12 or
            any(type(v) is not str or not v for v in required) or
            len(set(required))!=12):
            raise JeevesAppwideError("canonical enterprise journey denominator drift")
        journeys=contract.get("journeys")
        if type(journeys) is not list or len(journeys)!=12:
            raise JeevesAppwideError("twelve exact enterprise journey contracts required")
        gate_rows=docs[GATES].get("gates")
        if type(gate_rows) is not list or len(gate_rows)!=26 or any(
            type(row) is not dict or
            row.get("required_for_terminal_p1_promotion") is not True
            for row in gate_rows):
            raise JeevesAppwideError("required 26 release gates were reduced")
        gate_ids=[row.get("id") for row in gate_rows]
        if (any(type(g) is not str or not g for g in gate_ids)
            or len(set(gate_ids))!=26):
            raise JeevesAppwideError("duplicate or invalid release gate authority")
        caps=docs[CAPABILITIES].get("capabilities")
        if type(caps) is not list or len(caps)!=9:
            raise JeevesAppwideError("canonical nine AI product capabilities missing")
        cap_ids=[cap.get("capability_id") for cap in caps if type(cap) is dict]
        if len(cap_ids)!=9 or len(set(cap_ids))!=9 or any(
            type(k) is not str or not k for k in cap_ids):
            raise JeevesAppwideError("duplicate or invalid AI capability authority")
        workstreams=enterprise.get("implementation_workstreams")
        if type(workstreams) is not list or len(workstreams)!=16:
            raise JeevesAppwideError("sixteen independent enterprise workstreams missing")
        work_ids=[item.get("id") for item in workstreams if type(item) is dict]
        if len(set(work_ids))!=16 or len(work_ids)!=16 or any(
            type(k) is not str or not k for k in work_ids):
            raise JeevesAppwideError("invalid enterprise workstream authority")
        seen=set()
        normalized=[]
        tests={}
        for n,row in enumerate(journeys):
            if type(row) is not dict:
                raise JeevesAppwideError("enterprise journey entry must be an object")
            name=row.get("id")
            family_ids=row.get("family_ids")
            candidate_paths=row.get("source_test_candidates")
            target=row.get("acceptance_target")
            if (name!=JOURNEY_IDS[n] or name in seen
                or row.get("canonical_journey")!=required[n]
                or type(family_ids) is not list or not 2<=len(family_ids)<=8
                or any(type(v) is not str for v in family_ids)
                or len(set(family_ids))!=len(family_ids)
                or not set(family_ids)<=FAMILY_IDS
                or type(candidate_paths) is not list or not 1<=len(candidate_paths)<=6
                or any(type(v) is not str for v in candidate_paths)
                or len(set(candidate_paths))!=len(candidate_paths)
                or type(target) is not str or not 30<=len(target)<=400
                or row.get("acceptance_axes")!=list(AXES)
                or row.get("acceptance_receipts")!=[]
                or row.get("release_qualified") is not False
                or row.get("operator_review_required") is not True):
                raise JeevesAppwideError("unreviewed enterprise journey or forged signoff")
            seen.add(name)
            evidence=[]
            for path in candidate_paths:
                if type(path) is not str or not TEST_PATH.fullmatch(path):
                    raise JeevesAppwideError("non-curated enterprise journey test path")
                if path not in tests:
                    value=inv._safe_file(path,max_size=MAX_TEST_BYTES)
                    tests[path]={
                        "path":path,
                        "sha256":sha256(value.encode("utf-8")).hexdigest(),
                        "declared_test_functions":_test_case_count(value,path),
                    }
                evidence.append(tests[path])
            normalized.append({
                "id":name,
                "canonical_journey":required[n],
                "family_ids":family_ids,
                "acceptance_target":target,
                "candidate_test_sources":evidence,
                "candidate_test_files_located":len(evidence),
                "required_axes":list(AXES),
                "axis_status":{axis:"unverified" for axis in AXES},
                "independently_verified_axes":0,
                "missing_acceptance_axes":len(AXES),
                "tests_actually_executed_by_this_reader":False,
                "journey_release_qualified":False,
                "operator_review_required":True,
            })
        overview={
            "schema":SCHEMA,
            "inventory_snapshot":inv._digest,
            "source_receipts":sources,
            "contract_sha256":sources[CONTRACT],
            "canonical_journey_count":12,
            "required_acceptance_axes_per_journey":len(AXES),
            "total_journey_acceptance_axes":12*len(AXES),
            "independently_verified_journey_axes_observed":0,
            "unknown_journey_acceptance_axes":12*len(AXES),
            "source_linked_journeys":len(normalized),
            "unique_candidate_test_file_count":len(tests),
            "unique_candidate_test_function_declarations":sum(
                row["declared_test_functions"] for row in tests.values()),
            "journeys_release_qualified_observed":0,
            "required_terminal_gates":len(gate_ids),
            "required_terminal_gate_ids":gate_ids,
            "real_exact_head_gate_successes_observed":None,
            "AI_capability_contract_total":len(cap_ids),
            "AI_capability_ids":cap_ids,
            "AI_capabilities_real_product_qualified_observed":None,
            "enterprise_workstreams":len(work_ids),
            "enterprise_workstream_ids":work_ids,
            "workstream_exit_requirements_verified_observed":None,
            "full_app_completion_percent":None,
            "actual_app_release_qualified":False,
            "source_presence_is_not_journey_execution":True,
            "unverified_is_not_failed":True,
            "human_approval_not_inferred":True,
            "release_requires_external_independent_evidence":True,
            "source_edits_performed":False,
        }
        return {**overview,"digest":digest(overview)},normalized

    def overview(self,*,expected_snapshot=None,expected_contract_sha256=None):
        overview,_=self._build(expected_snapshot=expected_snapshot,
                               expected_contract_sha256=expected_contract_sha256)
        return overview

    def page(self,*,offset=0,limit=6,expected_report_digest=None,
             expected_snapshot=None,expected_contract_sha256=None):
        if type(offset) is not int or not 0<=offset<=12:
            raise JeevesAppwideError("bounded enterprise journey offset required")
        if type(limit) is not int or not 1<=limit<=MAX_PAGE:
            raise JeevesAppwideError("bounded enterprise journey page size required")
        overview,rows=self._build(expected_snapshot=expected_snapshot,
                                  expected_contract_sha256=expected_contract_sha256)
        if expected_report_digest is not None and expected_report_digest!=overview["digest"]:
            raise JeevesAppwideError("stale enterprise journey evidence source")
        selected=rows[offset:offset+limit]
        output={
            "schema":SCHEMA+".page",
            "report_digest":overview["digest"],
            "offset":offset,
            "limit":limit,
            "total_matches":len(rows),
            "next_offset":offset+len(selected) if offset+len(selected)<len(rows) else None,
            "journeys":selected,
            "release_qualification_not_claimed":True,
        }
        return {**output,"digest":digest(output)}
