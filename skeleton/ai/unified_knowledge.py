"""Unified bounded context for verified external evidence and isolated project memory."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json

from skeleton.ai.context.flgb_context_runtime import ContextItem, CompiledContext, compile_context
from skeleton.ai.memory_retrieval import MemoryContextBundle


class UnifiedKnowledgeError(ValueError): pass

def _digest(v):
    try: raw=json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()
    except (TypeError,ValueError,UnicodeError) as exc: raise UnifiedKnowledgeError("knowledge receipt not canonical") from exc
    return sha256(raw).hexdigest()

@dataclass(frozen=True)
class ExternalEvidence:
    evidence_id:str
    text:str
    content_digest:str
    provenance_digest:str
    token_cost:int
    priority:int=0
    def __post_init__(self):
        if sha256(self.text.encode()).hexdigest()!=self.content_digest:
            raise UnifiedKnowledgeError("external evidence content mismatch")
        if len(self.provenance_digest)!=64 or any(c not in "0123456789abcdef" for c in self.provenance_digest):
            raise UnifiedKnowledgeError("invalid external provenance digest")
        if isinstance(self.token_cost,bool) or not isinstance(self.token_cost,int) or self.token_cost<=0:
            raise UnifiedKnowledgeError("invalid external token cost")

@dataclass(frozen=True)
class UnifiedKnowledgeBundle:
    compiled:CompiledContext
    text:str
    text_digest:str
    external_ids:tuple[str,...]
    memory_ids:tuple[str,...]
    source_root_digest:str
    def __post_init__(self):
        if sha256(self.text.encode()).hexdigest()!=self.text_digest:
            raise UnifiedKnowledgeError("unified context text mismatch")
        if set(self.external_ids)&set(self.memory_ids):
            raise UnifiedKnowledgeError("knowledge source identity collision")

def compile_unified_knowledge(
    operation_id:str,
    external:tuple[ExternalEvidence,...],
    memory:MemoryContextBundle,
    *,
    token_budget:int,
)->UnifiedKnowledgeBundle:
    items=[]; values={}
    for e in external:
        if e.evidence_id in values: raise UnifiedKnowledgeError("duplicate external evidence id")
        values[e.evidence_id]=e.text
        items.append(ContextItem(e.evidence_id,"external-evidence",e.content_digest,e.provenance_digest,e.token_cost,e.priority,False))
    for r in memory.recalled:
        fid=r.fact.fact_id
        if fid in values: raise UnifiedKnowledgeError("external/memory identity collision")
        values[fid]=r.fact.value
        item=r.context_item
        items.append(ContextItem(item.item_id,"project-memory",item.content_digest,item.provenance_digest,item.token_cost,item.priority,False))
    compiled=compile_context(operation_id,tuple(items),token_budget=token_budget)
    selected=compiled.selected_ids
    text="\n\n".join(values[x] for x in selected)
    ext_ids=tuple(x for x in selected if any(e.evidence_id==x for e in external))
    mem_ids=tuple(x for x in selected if any(r.fact.fact_id==x for r in memory.recalled))
    root=_digest({
        "schema":"skeleton.ai.unified-knowledge-context.v1",
        "compiled_source_digest":compiled.source_digest,
        "external_ids":ext_ids,"memory_ids":mem_ids,
        "text_digest":sha256(text.encode()).hexdigest(),
    })
    return UnifiedKnowledgeBundle(compiled,text,sha256(text.encode()).hexdigest(),ext_ids,mem_ids,root)

__all__=["UnifiedKnowledgeError","ExternalEvidence","UnifiedKnowledgeBundle","compile_unified_knowledge"]
