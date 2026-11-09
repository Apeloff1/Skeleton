"""Deterministic ECS query predicates and stable result ordering."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Any
from .errors import QueryError
from .index import ComponentIndex
from .store import EntityStore
MAX_QUERY_COMPONENTS=64;MAX_PREDICATES=128;MAX_RESULTS=100_000
class CompareOp(str,Enum): EQ="eq";NE="ne";LT="lt";LE="le";GT="gt";GE="ge";IN="in";CONTAINS="contains"
@dataclass(frozen=True)
class FieldPredicate:
    schema_id:str;field:str;op:CompareOp;value:Any
    def __post_init__(self):
        if not self.schema_id or not self.field: raise QueryError("predicate identifiers must be non-empty")
        if not isinstance(self.op,CompareOp): object.__setattr__(self,"op",CompareOp(self.op))
    def matches(self,actual):
        try:
            return {CompareOp.EQ:lambda:actual==self.value,CompareOp.NE:lambda:actual!=self.value,CompareOp.LT:lambda:actual<self.value,CompareOp.LE:lambda:actual<=self.value,CompareOp.GT:lambda:actual>self.value,CompareOp.GE:lambda:actual>=self.value,CompareOp.IN:lambda:actual in self.value,CompareOp.CONTAINS:lambda:self.value in actual}[self.op]()
        except (TypeError,ValueError): return False
@dataclass(frozen=True)
class QuerySpec:
    all_of:tuple[str,...]=();any_of:tuple[str,...]=();none_of:tuple[str,...]=();predicates:tuple[FieldPredicate,...]=();limit:int=MAX_RESULTS;offset:int=0
    def __post_init__(self):
        for attr in ("all_of","any_of","none_of"):
            values=tuple(sorted(set(getattr(self,attr))));
            if len(values)>MAX_QUERY_COMPONENTS: raise QueryError("too many query components")
            object.__setattr__(self,attr,values)
        if len(self.predicates)>MAX_PREDICATES: raise QueryError("too many predicates")
        if isinstance(self.limit,bool) or not isinstance(self.limit,int) or not 0<=self.limit<=MAX_RESULTS: raise QueryError("invalid query limit")
        if isinstance(self.offset,bool) or not isinstance(self.offset,int) or self.offset<0: raise QueryError("invalid query offset")
@dataclass(frozen=True)
class QueryRow: entity_id:str;component_ids:tuple[str,...]
class QueryEngine:
    def __init__(self,store:EntityStore,*,index:ComponentIndex|None=None): self.store=store;self.index=index
    def _candidates(self,spec):
        if self.index is None:return self.store.entity_ids()
        self.index.require_current(self.store);c=set(self.index.candidates_all(spec.all_of)) if spec.all_of else set(self.store.entity_ids())
        if spec.any_of:c&=set(self.index.candidates_any(spec.any_of))
        if spec.none_of:c-=set(self.index.candidates_any(spec.none_of))
        return tuple(sorted(c))
    def execute(self,spec:QuerySpec)->tuple[QueryRow,...]:
        rows=[]
        for eid in self._candidates(spec):
            comps=set(self.store.component_ids(eid))
            if spec.all_of and not set(spec.all_of)<=comps:continue
            if spec.any_of and not(set(spec.any_of)&comps):continue
            if spec.none_of and set(spec.none_of)&comps:continue
            matched=True
            for p in spec.predicates:
                if not self.store.has_component(eid,p.schema_id):matched=False;break
                data=self.store.get_component(eid,p.schema_id).data
                if p.field not in data or not p.matches(data[p.field]):matched=False;break
            if matched:rows.append(QueryRow(eid,self.store.component_ids(eid)))
        return tuple(rows[spec.offset:spec.offset+spec.limit])
    def ids(self,spec):return tuple(r.entity_id for r in self.execute(spec))
    def count(self,spec):return len(self.execute(spec))
