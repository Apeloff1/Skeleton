from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime,timezone
from types import SimpleNamespace
from uuid import uuid4
import asyncio
import sqlite3
import pytest
from core.conversations import MongoConversationAuthority, _message_doc
from core.dragon_conversation_binding import DragonConversationBinding, install_dragon_conversation_binding
from skeleton.contracts.conversation import ConversationThread, ConversationThreadState, ConversationMessage, ConversationAuthorType
from skeleton.contracts.context import ContextTrust, ContextKind


def fixtures(tmp_path):
    now=datetime.fromtimestamp(10,timezone.utc)
    thread=ConversationThread(str(uuid4()),'tenant','alice@example.test',now,now,11,10,str(uuid4()),title='Game design')
    messages=tuple(ConversationMessage(str(uuid4()),thread.thread_id,thread.active_branch_id,i,ConversationAuthorType.USER,
        now,'step-'+str(i),content='secret transcript text '+str(i)) for i in range(1,11))
    @contextmanager
    def connections():
        db=sqlite3.connect(tmp_path/'context.sqlite',timeout=.05)
        try: yield db
        finally: db.close()
    policy={'tenant':thread.tenant_id,'owner':thread.owner_id,'thread':thread.thread_id,
        'retention_consent':True,'training_consent':False,'expires_at':1000,'factors':{'engine':'godot','genre':'platformer'}}
    async def reader(_thread): return dict(policy)
    binding=DragonConversationBinding(connections,reader,clock=lambda:10)
    return thread,messages,connections,policy,binding


@pytest.mark.asyncio
async def test_real_disk_checkpoint_context_restart_and_no_transcript(tmp_path):
    thread,messages,connections,policy,binding=fixtures(tmp_path)
    digest=await binding.after_commit(thread,messages)
    assert len(digest)==64
    assert await binding.after_commit(thread,messages)==digest
    segments=await binding.context_segments(thread,'godot')
    assert len(segments)==1 and segments[0].trust_level is ContextTrust.DERIVED_UNTRUSTED
    assert 'secret transcript' not in segments[0].content
    assert 'training_eligible":false' in segments[0].content
    with connections() as db:
        assert db.execute('SELECT count(*) FROM dragon_conversation_micro_logs').fetchone()[0]==1
    reopened=DragonConversationBinding(connections,binding.policy_reader,clock=lambda:10)
    assert (await reopened.context_segments(thread,'platformer'))[0].content_digest==segments[0].content_digest


@pytest.mark.asyncio
async def test_current_consent_expiry_owner_and_branch_gates(tmp_path):
    thread,messages,connections,policy,binding=fixtures(tmp_path)
    policy['retention_consent']=False
    assert await binding.after_commit(thread,messages) is None
    policy['retention_consent']=True
    binding.clock=lambda:311  # Re-consent waits out the short in-flight revocation fence.
    await binding.after_commit(thread,messages)
    policy['expires_at']=10
    assert await binding.context_segments(thread,'godot')==()
    policy['expires_at']=1000
    assert await binding.context_segments(replace(thread,active_branch_id=str(uuid4())),'godot')==()
    with pytest.raises(PermissionError): await binding.context_segments(replace(thread,owner_id='other'),'godot')
    policy['retention_consent']=False
    assert await binding.context_segments(thread,'godot')==()


@pytest.mark.asyncio
async def test_delete_fence_prevents_late_checkpoint_resurrection(tmp_path):
    thread,messages,connections,policy,binding=fixtures(tmp_path)
    await binding.after_commit(thread,messages)
    await binding.delete_thread(thread.tenant_id,thread.owner_id,thread.thread_id)
    assert await binding.context_segments(thread,'godot')==()
    with pytest.raises(PermissionError,match='fence'):
        await binding.after_commit(thread,messages)
    with connections() as db:
        assert db.execute('SELECT count(*) FROM dragon_conversation_micro_terms').fetchone()[0]==0


class Cursor:
    def __init__(self,rows): self.rows=rows
    def sort(self,*_): return self
    def limit(self,*_): return self
    async def to_list(self,**_): return self.rows


def authority_for(thread,messages,binding):
    authority=object.__new__(MongoConversationAuthority)
    authority.dragon_projection=binding
    authority.dragon_projection_outcomes={'written':0,'skipped':0,'degraded':0}
    captured=[]
    def find(query,fields):
        assert 'content' not in fields
        captured.append(query)
        return Cursor([{k:v for k,v in _message_doc(m).items() if k in fields} for m in messages])
    authority.messages=SimpleNamespace(find=find)
    return authority,captured


@pytest.mark.asyncio
async def test_canonical_ten_step_hook_reads_only_reference_metadata(tmp_path):
    thread,messages,_,_,binding=fixtures(tmp_path)
    authority,captured=authority_for(thread,messages,binding)
    await authority._project_dragon_checkpoint(thread,messages[8])
    assert captured==[]
    await authority._project_dragon_checkpoint(thread,messages[9])
    assert captured[0]['sequence']=={'$gt':0,'$lte':10}
    assert authority.dragon_projection_outcomes['written']==1
    assert len(await binding.context_segments(thread,'godot'))==1


@pytest.mark.asyncio
async def test_projection_failure_does_not_invalidate_canonical_commit(tmp_path):
    thread,messages,_,_,binding=fixtures(tmp_path)
    async def broken(*_): raise OSError('projection offline')
    binding.after_commit=broken
    authority,_=authority_for(thread,messages,binding)
    await authority._project_dragon_checkpoint(thread,messages[-1])
    assert authority.dragon_projection_outcomes['degraded']==1


@pytest.mark.asyncio
async def test_projection_timeout_is_bounded_and_cancelled(tmp_path):
    thread,messages,_,_,binding=fixtures(tmp_path)
    cancelled=[]
    async def blocked(*_):
        try: await asyncio.Event().wait()
        finally: cancelled.append(True)
    binding.after_commit=blocked
    authority,_=authority_for(thread,messages,binding)
    await authority._project_dragon_checkpoint(thread,messages[-1])
    assert cancelled==[True] and authority.dragon_projection_outcomes['degraded']==1


@pytest.mark.asyncio
async def test_canonical_append_calls_projection_after_commit_and_on_retry(tmp_path):
    thread,messages,_,_,binding=fixtures(tmp_path)
    authority,captured=authority_for(thread,messages,binding)
    inserted=[]
    before=replace(thread,message_sequence=9,version=10)
    async def recover(*_,**__): return thread if inserted else before
    async def idempotency(*_,**__): return messages[-1] if inserted else None
    async def insert(doc): inserted.append(doc)
    authority._recover_prepared=recover
    authority._message_by_idempotency=idempotency
    authority.messages.insert_one=insert
    authority.storage_admitter=None;authority.governance_registrar=None
    for _ in range(2):
        committed,message=await authority.append_message(messages[-1],tenant_id=thread.tenant_id,owner_id=thread.owner_id,expected_thread_version=10)
        assert committed==thread and message==messages[-1]
    assert len(inserted)==1 and len(captured)==2
    assert authority.dragon_projection_outcomes['written']==2


@pytest.mark.asyncio
async def test_context_revalidates_canonical_branch_and_rejects_control_injection(tmp_path):
    thread,messages,_,_,binding=fixtures(tmp_path)
    await binding.after_commit(thread,messages)
    authority,_=authority_for(thread,messages,binding)
    async def current(*_,**__): return thread
    authority.get_thread=current
    assert len(await authority.dragon_context_segments(thread,'godot'))==1
    segment=(await binding.context_segments(thread,'godot'))[0]
    async def injected(*_): return (replace(segment,trust_level=ContextTrust.TRUSTED_CONTROL,kind=ContextKind.SYSTEM_POLICY),)
    binding.context_segments=injected
    assert await authority.dragon_context_segments(thread,'godot')==()


@pytest.mark.asyncio
async def test_governed_delete_cleans_projection_before_parent_removal(tmp_path):
    thread,messages,connections,_,binding=fixtures(tmp_path)
    await binding.after_commit(thread,messages)
    authority,_=authority_for(thread,messages,binding)
    async def parent(*_,**__): return {'owner_id':thread.owner_id}
    authority.threads=SimpleNamespace(find_one=parent)
    await authority._delete_dragon_projection('thread',{'_id':thread.thread_id},thread.tenant_id)
    assert await binding.context_segments(thread,'godot')==()
    with connections() as db:
        assert db.execute('SELECT count(*) FROM dragon_conversation_micro_fences').fetchone()[0]==1


def test_binding_installation_cannot_reset_existing_projection(tmp_path):
    *_,binding=fixtures(tmp_path)
    authority=SimpleNamespace(dragon_projection=None)
    install_dragon_conversation_binding(authority,binding)
    with pytest.raises(ValueError): install_dragon_conversation_binding(authority,binding)


@pytest.mark.asyncio
async def test_checkpoint_is_selected_in_actual_chat_context_without_becoming_control(tmp_path):
    from routes.ai import _compile_chat_context
    thread,messages,_,_,binding=fixtures(tmp_path)
    await binding.after_commit(thread,messages)
    segments=await binding.context_segments(thread,'godot')
    current=replace(messages[-1],message_id=str(uuid4()),sequence=11,idempotency_key='current',content='Godot platformer design')
    thread=replace(thread,message_sequence=11,version=12)
    envelope=_compile_chat_context(thread=thread,transcript=messages+(current,),user_message=current,
        tenant_id=thread.tenant_id,operation_id=str(uuid4()),execution_id=str(uuid4()),request_context=None,dragon_segments=segments)
    selected=[s for s in envelope.selected_segments if s.source_type=='dragon_micro_checkpoint']
    assert len(selected)==1 and selected[0].trust_level is ContextTrust.DERIVED_UNTRUSTED
    assert all(s.source_type!='dragon_micro_checkpoint' for s in envelope.instruction_segments)


@pytest.mark.asyncio
async def test_bounded_repair_after_projection_loss_reauthorizes_canonical_window(tmp_path):
    thread,messages,_,_,binding=fixtures(tmp_path)
    authority,captured=authority_for(thread,messages,binding)
    async def current(*_,**kwargs):
        assert kwargs=={'tenant_id':thread.tenant_id,'owner_id':thread.owner_id}
        return thread
    authority.get_thread=current
    assert await authority.repair_dragon_checkpoint(thread.thread_id,tenant_id=thread.tenant_id,owner_id=thread.owner_id,end_sequence=10)=='written'
    assert len(captured)==1 and len(await binding.context_segments(thread,'godot'))==1
    with pytest.raises(ValueError):
        await authority.repair_dragon_checkpoint(thread.thread_id,tenant_id=thread.tenant_id,owner_id=thread.owner_id,end_sequence=20)


@pytest.mark.asyncio
async def test_deletion_fence_coarsens_without_denial_or_unbounded_metadata(tmp_path):
    from skeleton.ai.webcrawler.dragon_conversation_micro_logs import DragonConversationMicroLogs
    thread,messages,connections,_,binding=fixtures(tmp_path)
    with connections() as db:
        store=DragonConversationMicroLogs(db)
        db.executemany('INSERT INTO dragon_conversation_micro_fences VALUES(?,?,?,?)',
            ((thread.tenant_id,thread.owner_id,str(uuid4()),310) for _ in range(1000)))
        db.commit()
        store.delete_thread(thread.tenant_id,thread.owner_id,thread.thread_id,authorized=True,now=10)
        assert db.execute('SELECT count(*) FROM dragon_conversation_micro_fences').fetchone()[0]==1
    with pytest.raises(PermissionError): await binding.after_commit(thread,messages)


@pytest.mark.asyncio
async def test_long_canonical_owner_identity_can_delete_its_derived_data(tmp_path):
    thread,messages,connections,policy,binding=fixtures(tmp_path)
    owner='a'*180+'@example.test'
    thread=replace(thread,owner_id=owner);policy['owner']=owner
    await binding.after_commit(thread,messages)
    await binding.delete_thread(thread.tenant_id,owner,thread.thread_id)
    assert await binding.context_segments(thread,'godot')==()
