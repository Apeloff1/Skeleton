"""Consented Dragon projection of committed canonical conversation references.

The injected policy_reader must resolve CURRENT canonical retention consent,
not a request-body flag or a cached model claim. No hidden reasoning, raw message
text, provider transport, automatic training or authoritative memory promotion.
"""
from __future__ import annotations
from datetime import datetime, timezone
from hashlib import sha256
import json
from math import isfinite
from uuid import NAMESPACE_URL, uuid5
import time

from skeleton.ai.webcrawler.dragon_conversation_micro_logs import DragonConversationMicroLogs
from skeleton.contracts.conversation import ConversationThreadState
from skeleton.contracts.context import ContextSegment, ContextKind, ContextTrust, estimate_tokens


class DragonConversationBinding:
    def __init__(self, connection_factory, policy_reader, *, clock=time.time):
        self.connection_factory = connection_factory
        self.policy_reader = policy_reader
        self.clock = clock

    async def _policy(self, thread):
        if thread.state is not ConversationThreadState.ACTIVE:
            return None
        policy = await self.policy_reader(thread)
        if policy is None:
            return None
        if not isinstance(policy, dict) or (policy.get('tenant'),policy.get('owner'),policy.get('thread')) != (thread.tenant_id,thread.owner_id,thread.thread_id):
            raise PermissionError('canonical conversation policy identity mismatch')
        if policy.get('retention_consent') is not True:
            if policy.get('retention_consent') is False:
                await self.delete_thread(thread.tenant_id,thread.owner_id,thread.thread_id)
            return None
        if not isinstance(policy.get('training_consent',False),bool):
            raise ValueError('invalid separate training consent')
        expiry=policy.get('expires_at')
        now=self.clock()
        if isinstance(expiry,bool) or not isinstance(expiry,(int,float)) or not isfinite(expiry) or not now < expiry <= now+7*86400:
            return None
        factors=policy.get('factors')
        if not isinstance(factors,dict):
            raise ValueError('explicit game facets required')
        return policy

    async def after_commit(self, thread, window):
        policy=await self._policy(thread)
        if policy is None:
            return None
        with self.connection_factory() as db:
            store=DragonConversationMicroLogs(db)
            store.expire(now=self.clock())
            return store.checkpoint(thread,window,policy['factors'],tenant=thread.tenant_id,
                owner=thread.owner_id,expires_at=policy['expires_at'],authorized=True,
                retention_consent=True,training_consent=policy.get('training_consent',False),now=self.clock())

    async def delete_thread(self, tenant, owner, thread):
        with self.connection_factory() as db:
            DragonConversationMicroLogs(db).delete_thread(tenant,owner,thread,authorized=True,now=self.clock())

    async def context_segments(self, thread, query):
        policy=await self._policy(thread)
        if policy is None:
            return ()
        with self.connection_factory() as db:
            items=DragonConversationMicroLogs(db).retrieve(thread,query[:512],tenant=thread.tenant_id,
                owner=thread.owner_id,now=self.clock(),authorized=True,limit=3)
        segments=[]
        for item in items:
            # An old training flag never carries permission into a new request.
            item={**item,'training_eligible':False}
            content=json.dumps(item,sort_keys=True,separators=(',',':'),ensure_ascii=True)
            digest=sha256(content.encode()).hexdigest()
            source='dragon-conversation:'+thread.thread_id+':'+digest
            segments.append(ContextSegment(segment_id=str(uuid5(NAMESPACE_URL,source)),
                kind=ContextKind.CONVERSATION_SUMMARY,source_type='dragon_micro_checkpoint',
                source_id=source,content_ref=source,content_digest=digest,
                trust_level=ContextTrust.DERIVED_UNTRUSTED,data_class=thread.data_class,
                tenant_id=thread.tenant_id,purpose='model-inference',priority=750,relevance=.6,
                created_at=datetime.fromtimestamp(self.clock(),timezone.utc),token_estimate=estimate_tokens(content),
                provenance=tuple(item['message_refs']),retention_class='consented-conversation-projection',
                content=content,derived_from=tuple(item['message_refs'])))
        return tuple(segments)


def install_dragon_conversation_binding(authority, binding):
    if not isinstance(binding,DragonConversationBinding):
        raise ValueError('typed Dragon conversation binding required')
    if getattr(authority,'dragon_projection',None) is not None:
        raise ValueError('conversation projection already configured')
    authority.dragon_projection=binding
