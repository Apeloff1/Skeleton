"""Atomic model-result persistence: transcript, receipt, journal and outbox."""
from __future__ import annotations
import time,json
from hashlib import sha256
from .contracts import InferenceRequest,GenerationReceipt,SpineLimits,Conflict,IntegrityFailure,canonical,digest,hexdigest
from .principal import require_session
from .chain import append
from .outbox import emit
from .capacity.proofs import validate_decision, decision_digest

def _validate_result(req,limit,result):
    if not isinstance(result,GenerationReceipt):raise Conflict('backend did not return verified receipt')
    if result.model_sha256!=req.identity.model_sha256 or result.tokenizer_sha256!=req.identity.tokenizer_sha256:
        raise Conflict('model or tokenizer changed during generation')
    if result.generated_tokens>limit.max_output_tokens:raise Conflict('generation exceeds token ceiling')
    if result.prompt_tokens+result.generated_tokens>limit.context_tokens:raise Conflict('context budget overrun')
    if len(result.text.encode('utf8'))>limit.response_bytes:raise Conflict('response byte budget exceeded')

def commit(conn,req:InferenceRequest,limits:SpineLimits,result:GenerationReceipt,token:int,*,
           context_sha256:str,source_receipts:tuple[dict,...]=(),omitted_turns:int=0,
           capacity_report:dict|None=None)->dict:
    hexdigest(context_sha256,'context projection')
    if type(omitted_turns)is not int or not 0<=omitted_turns<=limits.max_history:
        raise Conflict('invalid omitted-history accounting')
    if len(source_receipts)>limits.max_sources:raise Conflict('unbounded evidence manifest')
    refs=[]
    for item in source_receipts:
        if not isinstance(item,dict) or 'source_id' not in item or 'sha256' not in item:
            raise Conflict('invalid evidence reference')
        hexdigest(item['sha256'],'source passage')
        refs.append({'id':item['source_id'],'revision':item['revision'],
                     'passage_sha256':item['sha256'],'document_sha256':item.get('document_sha256')})
    if capacity_report is not None:
        validate_decision(capacity_report)
        if (capacity_report['projection_sha256']!=context_sha256 or
            capacity_report['omitted_turns']!=omitted_turns or
            capacity_report['retained_sources']!=len(source_receipts)):
            raise Conflict('capacity and authoritative commit do not agree')
        recomputed=decision_digest(req.identity,limits,context_sha256,
            capacity_report['history_sha256'],
            capacity_report['candidate_evidence_sha256'],
            capacity_report['selected_evidence_sha256'],omitted_turns,
            capacity_report['omitted_sources'],
            capacity_report['token_admission'],
            capacity_report['native_prompt_tokens'])
        if recomputed!=capacity_report['proof_sha256']:
            raise Conflict('context capacity proof digest is invalid')
        if (capacity_report['token_admission']=='exact-backend-count-admitted'
            and capacity_report['native_prompt_tokens']!=result.prompt_tokens):
            raise Conflict('native tokenizer preflight and generation accounting disagree')
        expected_selected=[{'source':item['source_id'],
            'revision':item['revision'],'sha256':item['sha256']} for item in source_receipts]
        if sha256(canonical(expected_selected)).hexdigest()!=capacity_report['selected_evidence_sha256']:
            raise Conflict('capacity source digests disagree with committed evidence')
    _validate_result(req,limits,result)
    saved=require_session(conn,req.identity,req.session)
    if saved['state']!='open':raise Conflict('session closed before commit')
    old=conn.execute('SELECT revision,receipt_json,receipt_sha256 FROM turns WHERE session=? AND request_id=?',(req.session,req.request_id)).fetchone()
    if old:
        if sha256(old[1]).hexdigest()!=old[2]:raise IntegrityFailure('stored receipt tampered')
        return json.loads(old[1]) | {'replayed':True}
    now=time.monotonic_ns()
    row=conn.execute('SELECT request_sha256,state,owner_token,lease_deadline_ns FROM requests WHERE session=? AND request_id=?',(req.session,req.request_id)).fetchone()
    if row is None or row[0]!=req.bound_digest() or row[1]!='pending' or row[2]!=token or row[3] is None or now>=row[3]:
        raise Conflict('no current unexpired inference fence')
    revision=saved['revision']+1
    if revision>limits.max_history:raise Conflict('conversation turn budget exhausted')
    event={'schema':'spine.turn.v1','session':req.session,'request_id':req.request_id,
           'revision':revision,'request_sha256':req.bound_digest(),'output_sha256':result.output_digest(),
           'model_sha256':result.model_sha256,'tokenizer_sha256':result.tokenizer_sha256,
           'prompt_tokens':result.prompt_tokens,'generated_tokens':result.generated_tokens,
           'finish_reason':result.finish_reason,'principal':req.identity.key(),
           'context_sha256':context_sha256,'omitted_turns':omitted_turns,
           'evidence_refs':refs}
    if capacity_report is not None:
        event['context_capacity']=capacity_report
    raw=canonical(event)
    if conn.execute("UPDATE sessions SET revision=? WHERE session=? AND revision=? AND state='open'",
        (revision,req.session,saved['revision'])).rowcount!=1:raise Conflict('concurrent session revision update')
    conn.execute('INSERT INTO turns VALUES (?,?,?,?,?,?,?,?)',
        (req.session,req.request_id,revision,req.prompt.encode('utf8'),result.text.encode('utf8'),raw,sha256(raw).hexdigest(),now))
    if conn.execute("UPDATE requests SET state='committed',lease_deadline_ns=NULL,updated_ns=? WHERE session=? AND request_id=? AND owner_token=? AND state='pending'",
        (now,req.session,req.request_id,token)).rowcount!=1:raise Conflict('commit lost request token')
    append(conn,req.session,'turn_committed',event)
    emit(conn,f'turn_{req.session}_{req.request_id}',req.session,'ai_turn',event)
    return event | {'replayed':False}

def replay(conn,req:InferenceRequest)->dict|None:
    row=conn.execute('SELECT request_sha256,state FROM requests WHERE session=? AND request_id=?',(req.session,req.request_id)).fetchone()
    if not row:return None
    if row[0]!=req.bound_digest():raise Conflict('request ID reused with altered input')
    if row[1]!='committed':return None
    row=conn.execute('SELECT receipt_json,receipt_sha256,response FROM turns WHERE session=? AND request_id=?',(req.session,req.request_id)).fetchone()
    if not row:raise IntegrityFailure('committed request missing turn receipt')
    if sha256(row[0]).hexdigest()!=row[1]:raise IntegrityFailure('receipt digest mismatch')
    event=json.loads(row[0]);output=row[2].decode('utf8')
    if sha256(row[2]).hexdigest()!=event['output_sha256']:raise IntegrityFailure('response tamper detected')
    return event | {'text':output,'replayed':True}
