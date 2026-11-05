"""Read-only native operations doctor for a laptop whose GGUF cannot start.

The doctor uses the existing descriptor-anchored private SpineDatabase in
read-only mode. It audits queue, batch, telemetry and delivery tables and
cross-checks committed native receipts without loading GGUF, importing model
weights, starting AI worker processes, issuing network requests or deleting
uncertain state. Diagnostic output includes only digests, bounded counts and
hold codes, never prompts, answers, source filenames or approval secrets.

Integrity hashes detect isolated corruption but are NOT administrator-proof
signatures, and a clear result is NOT real physical model qualification.
"""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import sys
from typing import Any

from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import Identity
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.database import SpineDatabase

from .contracts import ContractHold,digest,exact_integer,fingerprint,identifier
from .durable_queue import WorkOrder
from .delivery_outbox import DeliveryIntent
from .telemetry_store import NativeObservation


class NativeColdFabricHold(ContractHold):
    """The offline native work chain is missing, inconsistent or unauthorized."""


def _table(conn,name):
    if conn.execute(
        "SELECT type FROM sqlite_master WHERE name=?",(name,),
    ).fetchone()!=("table",):
        raise NativeColdFabricHold("required native operations schema missing")


def _scope(identity):
    return identity.tenant,identity.subject,identity.model_sha256,identity.tokenizer_sha256


def _work(conn,identity,scope_sha256,maximum_rows):
    _table(conn,"jeeves_native_work_orders")
    rows=conn.execute(
        "SELECT order_id,scope_sha256,tenant,subject,model_sha256,"
        "tokenizer_sha256,session_id,request_id,prompt_sha256,seed,"
        "temperature_repr,cohort,priority,admitted_ns,expires_ns,"
        "state,revision,claim_sha256,native_output_sha256,"
        "receipt_sha256,reason,spec_sha256 "
        "FROM jeeves_native_work_orders "
        "WHERE tenant=? AND subject=? AND model_sha256=? AND tokenizer_sha256=? "
        "ORDER BY order_id LIMIT ?",
        (*_scope(identity),maximum_rows+1),
    ).fetchall()
    if len(rows)>maximum_rows:
        raise NativeColdFabricHold("unbounded native work inventory")
    counts=Counter()
    bound={}
    for row in rows:
        (oid,scope,tenant,subject,model,tokenizer,session,request,prompt,
         seed,temperature,cohort,priority,admitted,expires,state,
         revision,claim_sha,output_sha,receipt_sha,reason,spec_hash)=row
        try:
            order=WorkOrder(
                oid,scope,tenant,subject,model,tokenizer,
                session,request,prompt,seed,float(temperature),
                cohort,priority,admitted,expires,
            )
        except (TypeError,ValueError,OverflowError) as exc:
            raise NativeColdFabricHold("work-order typed record invalid") from exc
        if order.scope_sha256!=scope_sha256 or order.spec_sha256!=spec_hash:
            raise NativeColdFabricHold("work-order scope or immutable bytes differ")
        if state not in ("queued","claimed","held","committed","cancelled"):
            raise NativeColdFabricHold("unknown work-order state")
        exact_integer(revision)
        if state=="queued":
            if revision!=0 or claim_sha is not None or output_sha is not None:
                raise NativeColdFabricHold("queued work carries forbidden effect fields")
        elif state in ("claimed","held","committed"):
            digest(claim_sha)
            if revision<1:
                raise NativeColdFabricHold("claimed work lacks revision fence")
        if state=="committed":
            digest(output_sha)
            digest(receipt_sha)
            record=conn.execute(
                "SELECT r.state,t.receipt_json,t.receipt_sha256,t.response,"
                "s.principal FROM requests r "
                "JOIN sessions s ON s.session=r.session "
                "JOIN turns t ON t.session=r.session AND t.request_id=r.request_id "
                "WHERE r.session=? AND r.request_id=?",
                (session,request),
            ).fetchone()
            if record is None or record[0]!="committed":
                raise NativeColdFabricHold("committed work has no native receipt")
            native_state,payload,receipt_fingerprint,response,principal=record
            if (sha256(payload).hexdigest()!=receipt_fingerprint or
                sha256(response).hexdigest()!=output_sha or
                principal!=identity.key()):
                raise NativeColdFabricHold("work-native response custody differs")
            try:
                receipt=json.loads(payload)
            except (ValueError,UnicodeError,TypeError) as exc:
                raise NativeColdFabricHold("native committed receipt not parseable") from exc
            if receipt.get("output_sha256")!=output_sha:
                raise NativeColdFabricHold("native receipt output SHA differs from queue")
        elif state!="committed" and (output_sha is not None or receipt_sha is not None):
            raise NativeColdFabricHold("uncommitted work advertises output bytes")
        counts[state]+=1
        bound[oid]=(order,receipt_sha,output_sha,state)
    return counts,bound


def _deliveries(conn,identity,scope_sha256,maximum_rows,works):
    _table(conn,"jeeves_native_delivery_intents")
    rows=conn.execute(
        "SELECT delivery_id,scope_sha256,order_id,channel,output_sha256,"
        "work_receipt_sha256,nonce,created_ns,state,revision,"
        "claim_sha256,receiver_ack_sha256,spec_sha256 "
        "FROM jeeves_native_delivery_intents WHERE "
        "tenant=? AND subject=? AND model_sha256=? AND tokenizer_sha256=? "
        "ORDER BY delivery_id LIMIT ?",
        (*_scope(identity),maximum_rows+1),
    ).fetchall()
    if len(rows)>maximum_rows:
        raise NativeColdFabricHold("unbounded delivery inventory")
    counts=Counter()
    for row in rows:
        (did,scope,oid,channel,output,receipt,nonce,created,
         state,revision,claim_sha,ack_sha,spec_hash)=row
        try:
            intent=DeliveryIntent(
                did,scope,oid,channel,output,receipt,nonce,created,
            )
        except (ValueError,TypeError) as exc:
            raise NativeColdFabricHold("invalid signed delivery scope") from exc
        if intent.scope_sha256!=scope_sha256 or intent.fingerprint!=spec_hash:
            raise NativeColdFabricHold("delivery source and persisted spec differ")
        work=works.get(oid)
        if work is None or work[3]!="committed" or work[1]!=receipt or work[2]!=output:
            raise NativeColdFabricHold("delivery references missing committed work")
        exact_integer(revision)
        if state=="pending":
            if revision!=0 or claim_sha is not None or ack_sha is not None:
                raise NativeColdFabricHold("pending delivery has execution evidence")
        elif state=="claimed":
            digest(claim_sha)
            if ack_sha is not None or revision<1:
                raise NativeColdFabricHold("claimed delivery has impossible ack")
        elif state=="delivered":
            digest(claim_sha);digest(ack_sha)
            if revision<2:
                raise NativeColdFabricHold("delivery ack lacks monotonic fence")
        elif state=="cancelled":
            if claim_sha is not None or ack_sha is not None:
                raise NativeColdFabricHold("cancelled delivery may have been sent")
        else:
            raise NativeColdFabricHold("unknown delivery state")
        counts[state]+=1
    return counts


def _observations(conn,identity,maximum_rows):
    _table(conn,"jeeves_native_observations")
    rows=conn.execute(
        "SELECT observation_id,tenant,subject,model_sha256,tokenizer_sha256,"
        "session_id,request_id,prompt_sha256,output_sha256,generated_tokens,"
        "prompt_tokens,duration_ms,sampled_ns,sample_sha256 "
        "FROM jeeves_native_observations WHERE tenant=? AND subject=? "
        "AND model_sha256=? AND tokenizer_sha256=? ORDER BY observation_id LIMIT ?",
        (*_scope(identity),maximum_rows+1),
    ).fetchall()
    if len(rows)>maximum_rows:
        raise NativeColdFabricHold("unbounded telemetry history")
    for row in rows:
        try:
            sample=NativeObservation(*row[:-1])
        except (TypeError,ValueError) as exc:
            raise NativeColdFabricHold("malformed native telemetry sample") from exc
        if sample.fingerprint!=row[-1]:
            raise NativeColdFabricHold("native telemetry record checksum differs")
        original=conn.execute(
            "SELECT t.receipt_json,t.receipt_sha256,t.response,s.principal "
            "FROM turns t JOIN sessions s ON s.session=t.session "
            "WHERE t.session=? AND t.request_id=?",
            (sample.session_id,sample.request_id),
        ).fetchone()
        if original is None:
            raise NativeColdFabricHold("telemetry has no native committed turn")
        receipt_json,receipt_sha,response,principal=original
        if sha256(receipt_json).hexdigest()!=receipt_sha or principal!=identity.key():
            raise NativeColdFabricHold("telemetry source receipt corrupted")
        if sha256(response).hexdigest()!=sample.output_sha256:
            raise NativeColdFabricHold("telemetry output digest is not committed model result")
        try:
            decoded=json.loads(receipt_json)
        except (ValueError,TypeError,UnicodeError) as exc:
            raise NativeColdFabricHold("invalid telemetry source receipt") from exc
        if (decoded.get("generated_tokens")!=sample.generated_tokens or
            decoded.get("prompt_tokens")!=sample.prompt_tokens):
            raise NativeColdFabricHold("telemetry token measurements disagree with native")
    return len(rows)


def _batches(conn,identity,scope_sha256,maximum_rows):
    _table(conn,"jeeves_native_durable_batches")
    rows=conn.execute(
        "SELECT batch_id,scope_sha256,batch_sha256,job_count,state,created_ns "
        "FROM jeeves_native_durable_batches WHERE tenant=? AND subject=? "
        "AND model_sha256=? AND tokenizer_sha256=? ORDER BY batch_id LIMIT ?",
        (*_scope(identity),maximum_rows+1),
    ).fetchall()
    if len(rows)>maximum_rows:
        raise NativeColdFabricHold("unbounded native batch metadata")
    states=Counter()
    for bid,scope,batch_sha,count,state,created in rows:
        identifier(bid);digest(batch_sha)
        exact_integer(count,minimum=1,maximum=1000)
        exact_integer(created,maximum=10**30)
        if scope!=scope_sha256 or state not in ("admitting","ready"):
            raise NativeColdFabricHold("native batch scope or admission state changed")
        states[state]+=1
    return states


def _pending_native(conn,identity):
    rows=conn.execute(
        "SELECT r.state,COUNT(*) FROM requests r JOIN sessions s "
        "ON s.session=r.session WHERE s.principal=? GROUP BY r.state",
        (identity.key(),),
    ).fetchall()
    result={}
    for status,count in rows:
        if status not in ("pending","committed","held","cancelled"):
            raise NativeColdFabricHold("unknown native inference state")
        exact_integer(count)
        result[status]=count
    return result


def inspect_native_operations(
    *,state_dir:Path,tenant:str,subject:str,
    model_sha256:str,tokenizer_sha256:str,
    maximum_rows:int=10000,
)->dict[str,object]:
    """No model activation, native effect, file mutation or network call."""
    if not isinstance(state_dir,Path) or not state_dir.is_absolute() or ".." in state_dir.parts:
        raise NativeColdFabricHold("private absolute canonical state root required")
    if type(maximum_rows) is not int or not 1 <= maximum_rows <= 100000:
        raise NativeColdFabricHold("invalid bounded read-only audit inventory")
    identity=Identity(tenant,subject,model_sha256,tokenizer_sha256)
    from .contracts import Scope
    scope=Scope(tenant,subject,model_sha256,tokenizer_sha256)
    with SpineDatabase(state_dir,readonly=True) as db:
        with db.snapshot() as conn:
            work,by_id=_work(conn,identity,scope.binding,maximum_rows)
            delivery=_deliveries(conn,identity,scope.binding,maximum_rows,by_id)
            telemetry=_observations(conn,identity,maximum_rows)
            batches=_batches(conn,identity,scope.binding,maximum_rows)
            native=_pending_native(conn,identity)
            holds=[]
            if work["claimed"] or work["held"]:
                holds.append("work_unknown_or_claimed")
            if delivery["claimed"]:
                holds.append("delivery_unknown_or_claimed")
            if native.get("pending",0) or native.get("held",0):
                holds.append("native_inference_uncertain")
            if batches["admitting"]:
                holds.append("batch_admission_incomplete")
            if delivery["pending"]:
                holds.append("unsent_delivery_intents")
            return {
                "schema":"jeeves.native_fabric_cold_doctor.v1",
                "status":"readonly-inspected-not-native-activated",
                "scope_sha256":scope.binding,
                "model_sha256":model_sha256,
                "tokenizer_sha256":tokenizer_sha256,
                "work_order_counts":dict(work),
                "batch_counts":dict(batches),
                "delivery_counts":dict(delivery),
                "native_request_counts":native,
                "telemetry_samples":telemetry,
                "holds":holds,
                "unknown_effects_clear":not holds,
                "casebook_required_for_batch_replay":True,
                "user_prompts_read_but_not_disclosed":False,
                "model_inference_started":False,
                "model_rights_independently_verified":False,
                "device_pressure_qualified":False,
                "release_certified":False,
            }


def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(
        description="Read-only cold Jeeves native traffic and delivery doctor",
    )
    parser.add_argument("--state-dir",type=Path,required=True)
    parser.add_argument("--tenant",required=True)
    parser.add_argument("--subject",required=True)
    parser.add_argument("--model-sha256",required=True)
    parser.add_argument("--tokenizer-sha256",required=True)
    parser.add_argument("--maximum-rows",type=int,default=10000)
    args=parser.parse_args(argv)
    try:
        report=inspect_native_operations(
            state_dir=args.state_dir,
            tenant=args.tenant,subject=args.subject,
            model_sha256=args.model_sha256,
            tokenizer_sha256=args.tokenizer_sha256,
            maximum_rows=args.maximum_rows,
        )
        sys.stdout.write(json.dumps(
            report,sort_keys=True,ensure_ascii=False,allow_nan=False,
        )+"\n")
        return 0 if not report["holds"] else 3
    except (Exception,KeyboardInterrupt) as exc:
        sys.stderr.write(json.dumps({
            "schema":"jeeves.native_fabric_cold_doctor.v1",
            "status":"held",
            "error_class":type(exc).__name__,
            "real_native_inference_qualified":False,
            "release_certified":False,
        },sort_keys=True)+"\n")
        return 2


if __name__=="__main__":
    raise SystemExit(main())


__all__=["NativeColdFabricHold","inspect_native_operations","main"]
