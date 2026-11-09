"""Operator-only durable native batch CLI using the verified local GGUF stack.

The input is a bounded JSON casebook on stdin. Model and source bytes must
already be installed and rights-approved through the existing source-bound
installer. No prompts, model text, receiver keys or filesystem paths are
placed in argv, logs or diagnostic stderr. This command never installs
weights, creates signed evidence, grants model-authored tools or contacts
hosted inference providers.

Modes are distinct: admit metadata without generation; inspect without
generation; one bounded real native wave; or explicit replay-only orphan
reconciliation. A process failure does not trigger a retry.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import sys
from typing import Any

from skeleton.ai.runtime.operational_ai.laptop_runtime.startup import activate_checked
from skeleton.ai.runtime.operational_ai.authority.canonical import load_json

from .native_batch_runtime import NativeBatchPolicy, NativeBatchTask
from .native_fabric_supervisor import FabricJob
from .native_durable_batch import NativeDurableBatchConveyor
from .native_readiness import inspect_native_jeeves


class NativeDurableBatchCLIHold(ValueError):
    """Operator task inventory or source-verified model admission rejected."""


def parse_durable_jobs(raw:bytes):
    """Strict immutable operator intent; no model-provided filesystem paths."""
    if type(raw) is not bytes or not 1<=len(raw)<=262144:
        raise NativeDurableBatchCLIHold("bounded casebook stdin required")
    source=load_json(raw,ceiling=262144)
    if type(source) is not dict or set(source)!={"schema","batch_id","jobs"}:
        raise NativeDurableBatchCLIHold("unexpected durable batch casebook fields")
    if source["schema"]!="jeeves.native_durable_casebook.v1":
        raise NativeDurableBatchCLIHold("unknown durable batch casebook schema")
    batch_id=source["batch_id"]
    from skeleton.jeeves.native_fabric.contracts import identifier
    identifier(batch_id,"batch ID")
    entries=source["jobs"]
    if type(entries) is not list or not 1<=len(entries)<=64:
        raise NativeDurableBatchCLIHold("bounded 1-64 batch jobs required")
    jobs=[]
    ids=set()
    for item in entries:
        if type(item) is not dict or not {"task_id","prompt"}<=set(item) or not set(item)<={
            "task_id","prompt","cohort","priority","exact_output_sha256",
        }:
            raise NativeDurableBatchCLIHold("unexpected or absent task fields")
        task=NativeBatchTask(
            task_id=item["task_id"],prompt=item["prompt"],
            exact_output_sha256=item.get("exact_output_sha256"),
        )
        if task.task_id in ids:
            raise NativeDurableBatchCLIHold("duplicate task in operator casebook")
        ids.add(task.task_id)
        jobs.append(FabricJob(
            task=task,
            cohort=item.get("cohort","operator"),
            priority=item.get("priority",0),
        ))
    return batch_id,tuple(jobs)


def run(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(
        description="Approved restart-safe local Jeeves GGUF batch"
    )
    parser.add_argument("--model-root",type=Path,required=True)
    parser.add_argument("--state-dir",type=Path,required=True)
    parser.add_argument("--tenant",required=True)
    parser.add_argument("--subject",required=True)
    parser.add_argument("--approve-native",action="store_true",
                        help="Explicitly approve activation of trusted installed GGUF")
    parser.add_argument("--casebook-stdin",action="store_true")
    parser.add_argument("--mode",choices=("admit","inspect","wave","reconcile"),required=True)
    parser.add_argument("--max-new-calls",type=int,default=1)
    parser.add_argument("--context",type=int,default=4096)
    parser.add_argument("--max-output-tokens",type=int,default=1024)
    parser.add_argument("--threads",type=int,default=4)
    parser.add_argument("--gpu-layers",type=int,default=0)
    parser.add_argument("--capacity-root",type=Path)
    parser.add_argument("--capacity-budget-bytes",type=int,default=8000000000)
    args=parser.parse_args(argv)
    try:
        if not args.approve_native or not args.casebook_stdin:
            raise NativeDurableBatchCLIHold("operator model approval and stdin required")
        if type(args.max_new_calls) is not int or not 1<=args.max_new_calls<=64:
            raise NativeDurableBatchCLIHold("bounded native wave size required")
        raw=sys.stdin.buffer.read(262145)
        batch_id,jobs=parse_durable_jobs(raw)
        policy=NativeBatchPolicy(
            maximum_jobs=64,maximum_prompt_bytes=262144,
            maximum_reserved_output_tokens=65536,
            maximum_wall_seconds=1800,
            maximum_single_job_ms=300000,
            abort_on_failed_exact_predicate=True,
        )
        if len(jobs)*args.max_output_tokens>policy.maximum_reserved_output_tokens:
            raise NativeDurableBatchCLIHold("batch native token reservations exceed floor")
        stack,worker,installed=activate_checked(
            model_root=args.model_root,state_dir=args.state_dir,
            tenant=args.tenant,subject=args.subject,
            n_ctx=args.context,max_new_tokens=args.max_output_tokens,
            n_threads=args.threads,gpu_layers=args.gpu_layers,
            capacity_root=args.capacity_root,
            capacity_budget_bytes=args.capacity_budget_bytes,
            isolated=True,
        )
        with stack:
            readiness=inspect_native_jeeves(worker,installed)
            if not readiness.source_bridge_ready:
                raise NativeDurableBatchCLIHold("installed native model source not approved")
            runtime=NativeDurableBatchConveyor(
                worker,approved=True,policy=policy,
            )
            if args.mode=="admit":
                result=runtime.admit(batch_id,jobs).to_public_record()
            elif args.mode=="inspect":
                result=runtime.inspect(batch_id,jobs).to_public_record()
            elif args.mode=="wave":
                result=runtime.execute_admitted(
                    batch_id,jobs,maximum_new_calls=args.max_new_calls,
                )
            else:
                result=runtime.reconcile_orphans(
                    batch_id,jobs,operator_approved=True,
                )
        sys.stdout.write(json.dumps(
            result,sort_keys=True,ensure_ascii=False,allow_nan=False,
            separators=(",",":"),
        )+"\n")
        return 0
    except (Exception,KeyboardInterrupt) as exc:
        # User tasks, model bytes, key custody and raw exceptions may contain
        # private text. Publish only a bounded class, never str(exc).
        sys.stderr.write(json.dumps({
            "schema":"jeeves.native_durable_operator_cli_error.v1",
            "status":"held","error_class":type(exc).__name__,
            "physical_native_qualified":False,
            "release_certified":False,
        },sort_keys=True)+"\n")
        return 2


if __name__=="__main__":
    raise SystemExit(run())


__all__=["NativeDurableBatchCLIHold","parse_durable_jobs","run"]
