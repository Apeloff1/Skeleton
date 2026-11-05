"""One explicitly approved, source-signed REAL GGUF turn on the local laptop.

Unlike source-only unit suites, this command refuses to run without a real
installed model, trusted signed source manifest, independent environment key,
private SQLite admission and explicit operator --approve-native. It never
silently installs weights, falls back to a provider or retries native effects.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import secrets
import stat
import sys
import time

from .core.contracts import CognitionError,Scope,refuse,integer
from .core.grounded_work import (
    prepare,bind_work_order,submit_signed,execute_signed_once,
)
from .manifest_custody import verify_signed_manifest,ingest_authorized_sources
from skeleton.ai.runtime.operational_ai.work_orders.authorization import OperatorAuthority
from skeleton.ai.runtime.operational_ai.work_orders.store import WorkOrderStore
from skeleton.ai.runtime.operational_ai.work_orders.contracts import WorkOrderError
from skeleton.ai.runtime.operational_ai.laptop_runtime.startup import activate_checked
from skeleton.ai.runtime.operational_ai.laptop_runtime.result_protocol import verify_turn_receipt
from skeleton.ai.runtime.operational_ai.laptop_runtime.session_adapter import create

_KEY_RE=re.compile(r"[0-9a-f]{64,8192}\Z",re.ASCII)


def _environment_key():
    raw=os.environ.get("SKELETON_OFFLINE_OPERATOR_KEY_HEX","")
    if type(raw) is not str or len(raw)%2 or _KEY_RE.fullmatch(raw) is None:
        refuse("independent operator key missing or invalid")
    key=bytes.fromhex(raw)
    if not 32<=len(key)<=4096:
        refuse("operator key must contain 32 to 4096 bytes")
    return key


def _read_private_manifest(path):
    if not isinstance(path,Path) or not path.is_absolute():
        refuse("signed source manifest path must be absolute")
    flags=os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK
    from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.path_policy import open_private_root
    from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import SpineError
    try:
        parent_fd=open_private_root(path.parent)
        try:
            fd=os.open(path.name,flags,dir_fd=parent_fd)
        except BaseException:
            os.close(parent_fd)
            raise
    except (OSError,ValueError,SpineError) as exc:
        raise CognitionError("private signed source manifest cannot be opened") from exc
    try:
        st=os.fstat(fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_nlink!=1 or
            st.st_uid!=os.getuid() or st.st_mode&0o022 or
            not 1<=st.st_size<=32768):
            refuse("signed source manifest must be bounded private regular file")
        data=bytearray()
        while len(data)<=st.st_size:
            block=os.read(fd,min(65536,st.st_size+1-len(data)))
            if not block:break
            data.extend(block)
        end=os.fstat(fd)
        if (st.st_dev,st.st_ino,st.st_size,st.st_ctime_ns,st.st_mtime_ns)!=(
            end.st_dev,end.st_ino,end.st_size,end.st_ctime_ns,end.st_mtime_ns
        ) or len(data)!=st.st_size:
            refuse("signed source manifest modified while read")
        try:
            current=os.stat(path.name,dir_fd=parent_fd,follow_symlinks=False)
        except OSError as exc:
            raise CognitionError("private manifest path moved during read") from exc
        for field in ("st_dev","st_ino","st_size","st_mtime_ns","st_ctime_ns","st_mode"):
            if getattr(end,field)!=getattr(current,field):
                refuse("private manifest replaced after opening descriptor")
        return bytes(data)
    finally:
        os.close(fd)
        os.close(parent_fd)


def run(argv=None):
    parser=argparse.ArgumentParser(description="Signed-source, real local GGUF once")
    parser.add_argument("--model-root",type=Path,required=True)
    parser.add_argument("--state-dir",type=Path,required=True)
    parser.add_argument("--queue-dir",type=Path,required=True)
    parser.add_argument("--source-root",type=Path,required=True)
    parser.add_argument("--source-manifest",type=Path,required=True)
    parser.add_argument("--tenant",required=True)
    parser.add_argument("--subject",required=True)
    parser.add_argument("--approve-native",action="store_true")
    parser.add_argument("--prompt-stdin",action="store_true")
    parser.add_argument("--emit-answer",action="store_true")
    parser.add_argument("--context",type=int,default=2048)
    parser.add_argument("--max-new-tokens",type=int,default=128)
    parser.add_argument("--threads",type=int,default=4)
    parser.add_argument("--gpu-layers",type=int,default=0)
    parser.add_argument("--token-ceiling",type=int,default=16384)
    parser.add_argument("--capacity-root",type=Path)
    args=parser.parse_args(argv)
    try:
        if not args.approve_native or not args.prompt_stdin:
            refuse("explicit operator native approval and bounded stdin required")
        if type(args.token_ceiling) is not int or not 128<=args.token_ceiling<=100000000:
            refuse("bounded operator token ceiling required")
        key=_environment_key()
        now=int(time.time())
        signed=_read_private_manifest(args.source_manifest)
        manifest=verify_signed_manifest(signed,key,observed_at=now)
        if (manifest.scope.tenant,manifest.scope.subject)!=(args.tenant,args.subject):
            refuse("command principal differs from signed sources")
        if not all(p.is_absolute() for p in (
            args.model_root,args.state_dir,args.queue_dir,args.source_root
        )):
            refuse("all native and operator paths must be explicit absolute paths")
        raw_prompt=sys.stdin.buffer.read(8193)
        if len(raw_prompt)>8192:
            refuse("stdin prompt exceeds original byte ceiling")
        try:
            question=raw_prompt.decode("utf-8","strict").strip()
        except UnicodeError as exc:
            raise CognitionError("invalid original UTF8 user question") from exc
        # Source proof occurs before any potentially expensive native activation.
        index=ingest_authorized_sources(args.source_root,manifest,
                    scope=manifest.scope,observed_at=int(time.time()))
        stack,worker,installed=activate_checked(
            model_root=args.model_root,state_dir=args.state_dir,
            tenant=args.tenant,subject=args.subject,n_ctx=args.context,
            max_new_tokens=args.max_new_tokens,n_threads=args.threads,
            gpu_layers=args.gpu_layers,isolated=True,
            capacity_root=args.capacity_root,
        )
        with stack:
            actual=worker.spine.identity
            if (
                actual.tenant,actual.subject,
                actual.model_sha256,actual.tokenizer_sha256,
            )!=(
                manifest.scope.tenant,manifest.scope.subject,
                manifest.scope.model_sha256,manifest.scope.tokenizer_sha256,
            ):
                refuse("installed local model differs from signed source epoch")
            limit=min(32768,worker.spine.limits.input_bytes)
            grounded=prepare(index,manifest.scope,question,mode="lexical",
                limit=min(4,len(manifest.sources)),max_prompt_bytes=limit,
                grounding_required=True)
            session=create(worker)
            request_id="r_"+secrets.token_hex(16)
            job_id="j_"+secrets.token_hex(16)
            order=bind_work_order(grounded,job_id=job_id,session_id=session,
                request_id=request_id,max_output_tokens=args.max_new_tokens)
            authority=OperatorAuthority(key)
            with WorkOrderStore(args.queue_dir) as store:
                try:
                    current=store.budget(args.tenant)
                except WorkOrderError:
                    store.configure_budget(args.tenant,ceiling=args.token_ceiling,
                                           operator_approved=True)
                else:
                    if current["ceiling"]!=args.token_ceiling:
                        refuse("existing durable token ceiling needs explicit revision CAS")
                timestamp=int(time.time())
                approval=authority.issue(order,issued_at=timestamp,
                                         expires_at=timestamp+300,approved=True)
                submit_signed(grounded,index,store,authority,order,approval,
                              observed_at=int(time.time()))
                committed=execute_signed_once(grounded,index,store,worker,order)
                if committed["status"]!="committed":
                    refuse("native dispatch remains held for canonical reconciliation")
                # Exact canonical read-only replay is NOT another generation.
                replay=worker.spine.replay(session,request_id,grounded.prompt_text,
                                          seed=order.seed,temperature=order.sampler_temperature)
                result=verify_turn_receipt(replay,
                            model_sha256=actual.model_sha256,
                            tokenizer_sha256=actual.tokenizer_sha256)
                if result["replayed"] is not True or (
                    result["output_sha256"]!=committed["output_sha256"]
                ):
                    refuse("native committed replay differs from first output")
                payload={
                    "schema":"offline-source-grounded-native-result.v1",
                    "status":"signed-native-turn-committed-and-replayed",
                    "session_id":session,"request_id":request_id,
                    "model_sha256":actual.model_sha256,
                    "tokenizer_sha256":actual.tokenizer_sha256,
                    "prompt_sha256":grounded.prompt_sha256,
                    "source_receipt_sha256":grounded.source_receipt_sha256,
                    "output_sha256":result["output_sha256"],
                    "tokens_charged":committed["tokens_charged"],
                    "native_execution_via_canonical_supervisor":True,
                    "model_license_independently_proved_here":False,
                    "independent_semantic_grounding_proved":False,
                    "device_release_certified":False,
                }
                if args.emit_answer:
                    payload["answer"]=result["text"]
                print(json.dumps(payload,sort_keys=True,ensure_ascii=False))
                return 0
    except (Exception,KeyboardInterrupt) as exc:
        # Never echo the operator key, private file path, prompt or traceback.
        print(json.dumps({"status":"held","error_class":type(exc).__name__,
                          "release_certified":False},sort_keys=True),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(run())
