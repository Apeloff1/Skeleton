"""Context-bounded 100%-readiness blocker queue grounded in canonical authorities.

This intentionally does not compute a product completion percentage from
source, draft tests or signatures. It enumerates the independent *leaf proof
requirements*: 421 volume qualifications, 168 family stages, 84 journey axes,
26 exact-head gates, 16 workstream exits, nine consumer AI products and five
application services = 729 separate evidence obligations in the current repo.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256

from .jeeves_appwide_fabric import AppwideInventory,JeevesAppwideError,digest
from .jeeves_completion_census import _json_object
from .jeeves_enterprise_journey_frontier import JeevesEnterpriseJourneyFrontier,AXES
from .jeeves_measured_completion import STAGES

SCHEMA="skeleton.ai.product_release_execution_queue.v1"
MAX_PAGE=50
SOURCE={
    "masterplan":"machine/ai_master_plan.json",
    "manifest":"skeleton/app/manifest.json",
    "enterprise":"machine/enterprise_system_architecture.json",
    "gates":"machine/p1_required_gate_authority.json",
    "capabilities":"machine/ai_capabilities.json",
    "scope":"machine/app_completion_scope.json",
}
KIND_PRIORITY={
    "release_gate":0,
    "ai_product":1,
    "enterprise_journey_axis":2,
    "family_acceptance_stage":3,
    "runtime_service":4,
    "enterprise_workstream":5,
    "volume_enterprise_qualification":6,
}


class JeevesReleaseExecutionQueue:
    def __init__(self, inventory):
        if not isinstance(inventory,AppwideInventory):
            raise JeevesAppwideError("source-pinned inventory required")
        inventory._require_scanned()
        self.inv=inventory

    def _report(self, expected_snapshot=None):
        if expected_snapshot is not None and self.inv._digest!=expected_snapshot:
            raise JeevesAppwideError("stale 100-percent release queue source")
        frontier=JeevesEnterpriseJourneyFrontier(self.inv)
        cross=frontier.overview(expected_snapshot=expected_snapshot)
        docs={}
        receipts={}
        for kind,path in SOURCE.items():
            text=self.inv._safe_file(path,max_size=1_000_000)
            docs[kind]=_json_object(text,path)
            receipts[path]=sha256(text.encode("utf-8")).hexdigest()
        tasks=[]
        def enqueue(kind,identity,target,owner):
            if type(identity) is not str or not identity or type(target) is not str:
                raise JeevesAppwideError("invalid independently verifiable obligation")
            tasks.append({
                "id":kind+":"+identity,
                "category":kind,
                "owner_id":owner,
                "acceptance_target":target,
                "priority":KIND_PRIORITY[kind],
                "evidence_status":"unverified",
                "evidence_present_in_source_reader":False,
                "failure_asserted_without_execution":False,
                "release_qualification_credited":False,
                "automatic_execution_authorized":False,
                "independent_operator_evidence_required":True,
            })
        for gate in docs["gates"]["gates"]:
            if type(gate) is not dict or gate.get(
                "required_for_terminal_p1_promotion") is not True:
                raise JeevesAppwideError("required gate cannot be omitted")
            enqueue("release_gate",gate["id"],
                    "Independently observed successful exact-head mandated gate",
                    gate["id"])
        for capability in docs["capabilities"]["capabilities"]:
            enqueue("ai_product",capability["capability_id"],
                    "Real trained/provisioned model outcome, safety, tool policy and durable user UX",
                    capability["capability_id"])
        for i,journey in enumerate(docs["enterprise"]["required_journeys"],1):
            for axis in AXES:
                enqueue("enterprise_journey_axis",
                        "J%02d"%i+":"+axis,
                        "Actual release journey: "+journey+" / "+axis,
                        "J%02d"%i)
        for family in docs["scope"]["families"]:
            for stage in STAGES[1:]:
                enqueue("family_acceptance_stage",family["id"]+":"+stage,
                        family["acceptance_target"]+" / independent "+stage,
                        family["id"])
        for service in docs["manifest"]["services"]:
            enqueue("runtime_service",service["name"],
                    "Real running service with health, persistence, auth, restart and client transport",
                    service["name"])
        for work in docs["enterprise"]["implementation_workstreams"]:
            enqueue("enterprise_workstream",work["id"],
                    "Verify real workstream exit criteria independently of implementation labels",
                    work["id"])
        volumes=docs["masterplan"]["volumes"]
        if (type(volumes) is not list or not 1<=len(volumes)<=1000
            or any(type(item) is not dict or type(item.get("id")) is not int
                   or item["id"]!=i or
                   type(item.get("key")) is not str
                   for i,item in enumerate(volumes))):
            raise JeevesAppwideError("canonical volume registry drift")
        for volume in volumes:
            enqueue("volume_enterprise_qualification",volume["key"],
                    "Independent verified runtime plus enterprise grade of "+volume["key"],
                    volume["key"])
        keys=[task["id"] for task in tasks]
        if len(set(keys))!=len(keys):
            raise JeevesAppwideError("duplicate release acceptance leaf identifier")
        tasks.sort(key=lambda task:(task["priority"],task["id"]))
        breakdown=dict(sorted(Counter(task["category"] for task in tasks).items()))
        expected_counts={
            "release_gate":26,"ai_product":9,"enterprise_journey_axis":84,
            "family_acceptance_stage":168,"runtime_service":5,
            "enterprise_workstream":16,"volume_enterprise_qualification":len(volumes),
        }
        if breakdown!=dict(sorted(expected_counts.items())):
            raise JeevesAppwideError("release evidence denominator source mismatch")
        body={
            "schema":SCHEMA,
            "inventory_snapshot":self.inv._digest,
            "enterprise_frontier_digest":cross["digest"],
            "source_sha256":receipts,
            "leaf_evidence_denominator":len(tasks),
            "category_leaf_breakdown":breakdown,
            "declared_volume_count":len(volumes),
            "product_family_denominator":42,
            "enterprise_journey_denominator":12,
            "mandatory_release_gate_denominator":26,
            "independent_leaf_proofs_verified_by_this_reader":0,
            "leaf_proofs_unverified_by_this_reader":len(tasks),
            "release_proven_from_this_source_scan":False,
            "full_app_completion_percent":None,
            "source_file_presence_not_accepted_as_test_or_release":True,
            "source_plan_signature_not_accepted_as_product_evidence":True,
            "no_parallel_unsafe_automatic_execution":True,
            "no_source_or_weights_modified":True,
        }
        return {**body,"digest":digest(body)},tasks

    def overview(self,*,expected_snapshot=None):
        report,_=self._report(expected_snapshot)
        return report

    def page(self,*,offset=0,limit=30,category=None,
             expected_queue_digest=None,expected_snapshot=None):
        if type(offset) is not int or not 0<=offset<=1000:
            raise JeevesAppwideError("bounded release work queue offset required")
        if type(limit) is not int or not 1<=limit<=MAX_PAGE:
            raise JeevesAppwideError("bounded release work queue page required")
        if category is not None and (
            type(category) is not str or category not in KIND_PRIORITY):
            raise JeevesAppwideError("unknown release acceptance category")
        report,tasks=self._report(expected_snapshot)
        if expected_queue_digest is not None and expected_queue_digest!=report["digest"]:
            raise JeevesAppwideError("release acceptance queue changed since review")
        if category:
            tasks=[t for t in tasks if t["category"]==category]
        chunk=tasks[offset:offset+limit]
        result={
            "schema":SCHEMA+".page",
            "queue_digest":report["digest"],
            "offset":offset,
            "limit":limit,
            "category":category,
            "total_matches":len(tasks),
            "next_offset":offset+len(chunk) if offset+len(chunk)<len(tasks) else None,
            "tasks":chunk,
            "release_signoff_not_claimed":True,
        }
        return {**result,"digest":digest(result)}
