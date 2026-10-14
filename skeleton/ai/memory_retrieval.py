"""Project-memory recall adapter for the canonical FLGB-03 context authority."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json

from skeleton.ai.context.flgb_context_runtime import ContextItem, CompiledContext, compile_context
from skeleton.ai.project_memory import ProjectFact, ProjectMemory


class MemoryRecallError(ValueError):
    pass


def _digest(value: object) -> str:
    try:
        raw=json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode("utf-8")
    except (TypeError,ValueError,UnicodeError) as exc:
        raise MemoryRecallError("memory recall is not canonically encodable") from exc
    return sha256(raw).hexdigest()


@dataclass(frozen=True)
class RecalledMemory:
    fact: ProjectFact
    context_item: ContextItem
    value_digest: str


@dataclass(frozen=True)
class MemoryContextBundle:
    recalled: tuple[RecalledMemory,...]
    compiled: CompiledContext
    text: str
    text_digest: str

    def __post_init__(self):
        if sha256(self.text.encode("utf-8")).hexdigest()!=self.text_digest:
            raise MemoryRecallError("memory context text digest mismatch")


def compile_project_memory_context(
    memory: ProjectMemory,
    *,
    tenant_id: str,
    project_id: str,
    trust_class: str,
    token_costs: dict[str,int],
    token_budget: int,
    operation_id: str,
) -> MemoryContextBundle:
    try:
        facts=memory.visible(tenant_id,project_id,trust_class)
    except PermissionError as exc:
        raise MemoryRecallError("memory read custody mismatch") from exc
    recalled=[]
    for fact in facts:
        cost=token_costs.get(fact.fact_id)
        if isinstance(cost,bool) or not isinstance(cost,int) or cost<=0:
            raise MemoryRecallError("positive token cost required for every visible fact")
        value_digest=sha256(fact.value.encode("utf-8")).hexdigest()
        provenance=_digest({
            "schema":"skeleton.ai.project-memory-context.v1",
            "fact_id":fact.fact_id,"source_id":fact.source_id,
            "tenant_id":fact.tenant_id,"project_id":fact.project_id,
            "trust_class":fact.trust_class,"value_digest":value_digest,
        })
        recalled.append(RecalledMemory(
            fact,
            ContextItem(
                item_id=fact.fact_id,kind="project-memory",
                content_digest=value_digest,provenance_digest=provenance,
                token_cost=cost,priority=0,mandatory=False,
            ),
            value_digest,
        ))
    if set(token_costs)!= {x.fact_id for x in facts}:
        raise MemoryRecallError("token cost map must exactly match visible memory")
    compiled=compile_context(operation_id,tuple(x.context_item for x in recalled),token_budget=token_budget)
    selected=set(compiled.selected_ids)
    selected_recalled=tuple(x for x in recalled if x.fact.fact_id in selected)
    text="\n\n".join(x.fact.value for x in selected_recalled)
    return MemoryContextBundle(
        recalled=selected_recalled,compiled=compiled,text=text,
        text_digest=sha256(text.encode("utf-8")).hexdigest(),
    )


__all__=["MemoryRecallError","RecalledMemory","MemoryContextBundle","compile_project_memory_context"]
