"""Actual local native AI durable work CLI (no fake production checkpoint).

The existing operational_ai.transport.cli build_service verifies the native
checkpoint, tokenizer, principal custody and authoritative chat store.
This program adds only a durable admission queue around that real service.

A genuinely approved checkpoint is required. No automatic network download,
model fabrication, public server or hosted-provider fallback is included.
"""
from __future__ import annotations
import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import secrets
import sqlite3
import sys
import time

from ..authority.canonical import ContractViolation, require_digest
from ..transport.cli import build_service
from .bridge import NativeJobBridge
from .db_file import open_private_job_store
from .errors import JobDenied, deny
from .spec import JobIdentity, JobSpec, WorkLimits, require_id


def trusted_clock_ms() -> int:
    return time.time_ns() // 1000000


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Private native AI durable job CLI")
    parser.add_argument("--checkpoint",required=True,type=Path)
    parser.add_argument("--sha256",required=True)
    parser.add_argument("--license",required=True)
    parser.add_argument("--tokenizer-sha256")
    parser.add_argument("--model-name",default="native")
    parser.add_argument("--tenant",default="local")
    parser.add_argument("--user",default="operator")
    parser.add_argument("--database",required=True,type=Path)
    parser.add_argument("--memory-db",required=True,type=Path)
    parser.add_argument("--journal-db",required=True,type=Path)
    parser.add_argument("--session")
    parser.add_argument("--system")
    parser.add_argument("--request-id")
    parser.add_argument("--job-id")
    parser.add_argument("--worker-id",default="local_worker")
    parser.add_argument("--max-new-tokens",type=int,default=64)
    parser.add_argument("--context-tokens",type=int,default=8192)
    parser.add_argument("--input-bytes",type=int,default=4096)
    parser.add_argument("--output-bytes",type=int,default=16384)
    parser.add_argument("--queue-name",default="durable_jobs")
    parser.add_argument("--deadline-ms",type=int,default=300000)
    parser.add_argument("--lease-ms",type=int,default=300000)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--message")
    mode.add_argument("--run-pending",action="store_true")
    mode.add_argument("--inspect-job",action="store_true")
    return parser


def main(argv:list[str]|None=None) -> int:
    parser=_parser()
    args=parser.parse_args(argv)
    if args.inspect_job and (not args.job_id or not args.session):
        parser.error("--inspect-job requires --job-id and --session")
    if args.message is not None and not args.message:
        parser.error("--message requires nonempty text")
    if args.system and args.session:
        parser.error("--system can only apply when a new session is created")
    try:
        require_digest(args.sha256)
        require_id(args.worker_id,"worker")
        require_id(args.queue_name,"queue")
        limits=WorkLimits(
            input_bytes=args.input_bytes,output_tokens=args.max_new_tokens,
            deadline_ms=args.deadline_ms,lease_ms=args.lease_ms,
        )
        with ExitStack() as stack:
            service=build_service(args,stack)
            root=args.database.absolute().parent
            store=stack.enter_context(open_private_job_store(root,args.queue_name,limits=limits))
            if args.message is not None:
                session=args.session or service.create(system=args.system)
                owner=JobIdentity(
                    service.actor.tenant,service.actor.user,session,
                    service.actor.model_digest,service.actor.tokenizer_digest,
                )
                now=trusted_clock_ms()
                job_id=args.job_id or "job_"+secrets.token_hex(12)
                existing=None
                if args.job_id:
                    try:
                        existing=store.load_spec(job_id,owner)
                    except JobDenied as exc:
                        if exc.code!="job-unknown":
                            raise
                if existing is None:
                    request=args.request_id or "req_"+secrets.token_hex(12)
                    spec=JobSpec(job_id,request,owner,args.message,now,
                                 now+limits.deadline_ms)
                    store.submit(spec,now_ms=now)
                else:
                    request=existing.request_id
                    if existing.question!=args.message:
                        deny("cli-idempotency-question")
                    if args.request_id is not None and args.request_id!=request:
                        deny("cli-idempotency-request")
                current=store.inspect(job_id,owner)
                replayed=current["state"]=="completed"
                if replayed:
                    result=store.receipt(job_id,owner)
                elif current["state"]=="pending":
                    result=NativeJobBridge(service,store).run_one(
                        args.worker_id,clock_ms=trusted_clock_ms,target_job_id=job_id,
                    )
                    if result is None:
                        deny("queue-no-admissible-job")
                else:
                    deny("cli-job-not-admissible")
                print(json.dumps({
                    "schema":"skeleton.ai.durable-cli.v1",
                    "session_id":session,"request_id":request,"job_id":job_id,
                    "model_sha256":owner.model_sha256,
                    "result":result.to_record(),
                    "replayed":replayed,
                    "native_model_tested":not replayed,
                    "release_certified":False,
                },ensure_ascii=False,sort_keys=True))
                return 0
            if args.inspect_job:
                owner=JobIdentity(
                    service.actor.tenant,service.actor.user,args.session,
                    service.actor.model_digest,service.actor.tokenizer_digest,
                )
                print(json.dumps(store.inspect(args.job_id,owner),sort_keys=True))
                return 0
            result=NativeJobBridge(service,store).run_one(
                args.worker_id,clock_ms=trusted_clock_ms,
            )
            print(json.dumps({
                "schema":"skeleton.ai.durable-cli.v1",
                "result":None if result is None else result.to_record(),
                "native_model_tested":result is not None,
                "release_certified":False,
            },ensure_ascii=False,sort_keys=True))
            return 0
    except (ContractViolation,JobDenied,ValueError,OSError,sqlite3.Error) as exc:
        print(json.dumps({"status":"blocked","reason":type(exc).__name__},
                         sort_keys=True),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
