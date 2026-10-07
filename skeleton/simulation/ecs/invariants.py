"""Read-only invariant inspection for ECS stores."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Any
from .canonical import digest
from .store import EntityStore
class FindingSeverity(str,Enum):INFO="info";WARNING="warning";ERROR="error"
@dataclass(frozen=True)
class InvariantFinding:code:str;severity:FindingSeverity;message:str;context:dict[str,Any]
@dataclass(frozen=True)
class InvariantReport:
    findings:tuple[InvariantFinding,...];store_digest:str;report_digest:str
    @property
    def ok(self):return not any(f.severity is FindingSeverity.ERROR for f in self.findings)
class InvariantInspector:
    def inspect(self,store:EntityStore)->InvariantReport:
        findings=[]
        if set(store.entity_ids())&set(store.tombstone_ids()):findings.append(InvariantFinding("live_tombstone_overlap",FindingSeverity.ERROR,"entity exists in live and tombstone sets",{}))
        for eid in store.entity_ids():
            record=store.get_entity(eid)
            if record.updated_revision<record.created_revision:findings.append(InvariantFinding("revision_regression",FindingSeverity.ERROR,"entity update precedes creation",{"entity_id":eid}))
            for sid in store.component_ids(eid):
                component=store.get_component(eid,sid)
                try:store.registry.get(component.schema_id,component.schema_version).validate(component.data)
                except Exception as exc:findings.append(InvariantFinding("component_invalid",FindingSeverity.ERROR,"component fails schema validation",{"entity_id":eid,"schema_id":sid,"error_type":type(exc).__name__}))
        material=[{"code":f.code,"severity":f.severity.value,"message":f.message,"context":f.context} for f in findings]
        return InvariantReport(tuple(findings),store.state_digest,digest({"store":store.state_digest,"findings":material}))
