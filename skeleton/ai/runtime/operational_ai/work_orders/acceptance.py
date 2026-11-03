"""Real installed GGUF -> signed durable work -> canonical replay -> integrity.

No synthetic model, implicit package installation, external provider,
tool-grant escalation or automatic native retry.
"""
from __future__ import annotations
import os
import secrets
from .contracts import identifier,prompt,refuse,WorkOrderError
from .model import WorkOrder
from .authorization import OperatorAuthority
from .ingress import SignedIngress
from .store import WorkOrderStore
from .executor import WorkOrderExecutor

def run_live(*,worker,queue_dir,tenant,subject,prompt_text,
             operator_key,token_ceiling=16384,now_seconds,
             max_output_tokens=128):
    identifier(tenant,"tenant")
    identifier(subject,"subject")
    prompt(prompt_text)
    if type(now_seconds) is not int or not 0<=now_seconds<=2**53-1:
        refuse("trusted operator clock required")
    if type(token_ceiling) is not int or not 128<=token_ceiling<=100000000:
        refuse("bounded durable native budget required")
    if type(max_output_tokens) is not int or not 1<=max_output_tokens<=8192:
        refuse("bounded native output requested")
    if (not hasattr(worker,"spine") or
        worker.spine.identity.tenant!=tenant or
        worker.spine.identity.subject!=subject):
        refuse("actual operator-identity model mismatch")
    worker.spine.backend  # True native worker is configured at installation/startup
    session="s_"+secrets.token_hex(16)
    session_created=worker.spine.create(session)
    if session_created!=session:
        refuse("canonical session allocation mismatch")
    request="r_"+secrets.token_hex(16)
    work=WorkOrder.bind(job_id="j_"+secrets.token_hex(16),
        tenant=tenant,subject=subject,
        model_sha256=worker.spine.identity.model_sha256,
        tokenizer_sha256=worker.spine.identity.tokenizer_sha256,
        session_id=session,request_id=request,prompt_text=prompt_text,
        max_output_tokens=max_output_tokens)
    work.confirm_worker(worker)
    signer=OperatorAuthority(operator_key)
    token=signer.issue(work,issued_at=now_seconds,
                       expires_at=now_seconds+300,approved=True)
    with WorkOrderStore(queue_dir) as queue:
        # Never reset already charged tokens on repeated laptop use.
        # A changed ceiling requires a separate explicit revision-CAS action.
        try:
            budget=queue.budget(tenant)
        except WorkOrderError:
            budget=queue.configure_budget(tenant,ceiling=token_ceiling,
                                          operator_approved=True)
        else:
            if budget["ceiling"]!=token_ceiling:
                refuse("existing token ceiling differs; explicit operator CAS required")
        SignedIngress(queue,signer).submit(work,token,observed_at=now_seconds)
        outcome=WorkOrderExecutor(queue,worker).run(work,prompt_text)
        audit=queue.audit()
        if outcome["status"]!="committed" or audit["jobs"]<1:
            refuse("native inference did not reach durable canonical commit")
        return {"schema":"offline-ai-native-work-acceptance.v1",
            "job_id":work.job_id,"session_id":session,
            "request_id":request,"model_sha256":work.model_sha256,
            "tokenizer_sha256":work.tokenizer_sha256,
            "output_sha256":outcome["output_sha256"],
            "charged_tokens":outcome["tokens_charged"],
            "source_state":"actual-supervisor-canonical-SQLite-replay",
            "outbox_pending":len(queue.pending_events(
                tenant=tenant,subject=subject,model_sha256=work.model_sha256)),
            "audit_head_sha256":audit["head_sha256"],
            "native_model_invoked":True,
            "independent_device_requalification":False,
            "release_certified":False}
