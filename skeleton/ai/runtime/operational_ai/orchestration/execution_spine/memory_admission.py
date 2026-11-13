"""Explicitly approved durable memory writes, independent from generated text."""
from __future__ import annotations
from .contracts import Identity,SpineError,identifier

def admit(memory,identity:Identity,source_id:str,content:str,*,approved:bool,
          rights:str,origin:str='operator',revision:int=1):
    if approved is not True:raise SpineError('memory requires independent owner approval')
    from skeleton.ai.runtime.operational_ai.context.sources import Source
    from skeleton.ai.runtime.operational_ai.authority.identity import Actor
    actor=Actor(identity.tenant,identity.subject,identity.model_sha256,identity.tokenizer_sha256)
    source=Source.create(source_id,identity.tenant,identity.subject,origin,content,
                         rights=rights,trust='user-supplied',revision=revision)
    memory.admit(actor,source,approved=True)
    return {'source_id':source.source_id,'sha256':source.digest,'revision':source.revision,
            'status':'operator-approved-scoped-memory'}

def forget(memory,identity:Identity,source_id:str,*,approved:bool)->bool:
    if approved is not True:raise SpineError('forget requires independent owner approval')
    from skeleton.ai.runtime.operational_ai.authority.identity import Actor
    actor=Actor(identity.tenant,identity.subject,identity.model_sha256,identity.tokenizer_sha256)
    return memory.forget(actor,identifier(source_id,'memory source'))
