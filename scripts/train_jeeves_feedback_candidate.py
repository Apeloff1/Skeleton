"""Train an isolated native adapter from an explicitly reviewed feedback export.

No serving process, remote model, network download, automatic promotion,
checkpoint rewrite, or activation. Requires separate artifact byte pins and
the native trainer's dataset-rights and heldout/token-contamination checks.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re

from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.model_runtime.runtime_contracts import DevicePolicy
from skeleton.ai.training.flgb_training_runtime import (
    AdapterTrainingRun, DatasetRevision, DatasetRights, TrainingContractError, digest_json,
)
from skeleton.ai.training.native_lora_specialization import (
    SpecializationPolicy, dataset_digest, train_specialization, publish_candidate,
)
from skeleton.app.jeeves_reviewed_feedback import _digest as feedback_digest
from skeleton.retrieval.learned_embeddings import _read_pinned

SCHEMA="skeleton.jeeves.specialization-input.v1"
MAX_EXPORT=4*1024*1024
MAX_CHECKPOINT=1024*1024**2
PIN=re.compile(r"[0-9a-f]{64}\Z")


def _pin(value):
    return type(value) is str and PIN.fullmatch(value) is not None


def _unique(pairs):
    result={}
    for key,value in pairs:
        if key in result:
            raise TrainingContractError("duplicate feedback export field")
        result[key]=value
    return result


def _constant(value):
    raise TrainingContractError("nonfinite feedback export field")


def validate_export(data):
    """Validate export identity, lineage, rights scope and dataset revision."""
    expected={"schema","session_id","source_revision","model_digest","tokenizer_digest",
              "train","heldout","lineage","dataset_rights","dataset_revision",
              "dataset_revision_digest","operator_rights_attested_not_independently_verified",
              "token_level_contamination_verified","training_performed","activation_authorized",
              "export_revocation_automatic","export_sha256"}
    if type(data) is not dict or set(data)!=expected or data["schema"]!=SCHEMA:
        raise TrainingContractError("unsupported reviewed feedback export")
    if (not all(_pin(data[key]) for key in ("model_digest","tokenizer_digest","dataset_revision_digest","export_sha256"))
            or data["export_sha256"]!=feedback_digest({k:v for k,v in data.items() if k!="export_sha256"})
            or data["operator_rights_attested_not_independently_verified"] is not True
            or any(data[key] is not False for key in ("token_level_contamination_verified","training_performed",
                                                      "activation_authorized","export_revocation_automatic"))):
        raise TrainingContractError("reviewed feedback export identity or state mismatch")
    train,heldout=data["train"],data["heldout"]
    content=dataset_digest(train,heldout)
    if len(train)>64 or len(heldout)>64 or len(set(train+heldout))!=len(train)+len(heldout):
        raise TrainingContractError("feedback split geometry or exact overlap")
    rights=DatasetRights(**data["dataset_rights"])
    revision=DatasetRevision(**data["dataset_revision"])
    if (not rights.permits("specialization") or rights.source_id!="local-reviewed-chat"
            or rights.license_id!="operator-attested" or revision.revision!=0
            or revision.dataset_id!=rights.dataset_id or revision.rights_digest!=rights.digest
            or revision.content_digest!=content or revision.digest!=data["dataset_revision_digest"]):
        raise TrainingContractError("dataset rights or revision binding mismatch")
    lineage=data["lineage"]
    if (type(lineage) is not list or len(lineage)!=len(train)+len(heldout)
            or digest_json(lineage)!=rights.evidence_digest):
        raise TrainingContractError("reviewed feedback lineage mismatch")
    seen_ids=set()
    seen_prompts=set()
    for items,split,offset in ((train,"train",0),(heldout,"heldout",len(train))):
        for i,text in enumerate(items):
            row=lineage[offset+i]
            if (type(row) is not dict or set(row)!={"feedback_id","split","feedback_sha256","prompt_sha256",
                    "target_sha256","rights_evidence_sha256"} or row["split"]!=split
                    or type(row["feedback_id"]) is not str or not row["feedback_id"]
                    or row["feedback_id"] in seen_ids or row["prompt_sha256"] in seen_prompts
                    or not all(_pin(row[k]) for k in ("feedback_sha256","prompt_sha256","target_sha256","rights_evidence_sha256"))):
                raise TrainingContractError("invalid or duplicate feedback lineage")
            if not text.startswith("user: "):
                raise TrainingContractError("invalid training message encoding")
            # User messages may contain the separator. Match the exact
            # source hashes rather than accepting the first split.
            separator="\nassistant: "
            matches=0
            start=6
            for _ in range(256):
                index=text.find(separator,start)
                if index<0:
                    break
                prompt=text[6:index]
                target=text[index+len(separator):]
                if (sha256(prompt.encode()).hexdigest()==row["prompt_sha256"] and
                        sha256(target.encode()).hexdigest()==row["target_sha256"]):
                    matches+=1
                start=index+len(separator)
            if matches!=1:
                raise TrainingContractError("feedback source text does not match lineage")
            seen_ids.add(row["feedback_id"])
            seen_prompts.add(row["prompt_sha256"])
    return rights,revision,train,heldout


def train_export(runtime,data,*,run_id,targets,policy):
    rights,revision,train,heldout=validate_export(data)
    if runtime.model_digest!=data["model_digest"] or runtime.tokenizer.digest!=data["tokenizer_digest"]:
        raise TrainingContractError("feedback export belongs to another exact model or tokenizer")
    if (type(targets) is not tuple or not 1<=len(targets)<=32
            or len(set(targets))!=len(targets)):
        raise TrainingContractError("explicit bounded adapter targets required")
    run=AdapterTrainingRun(run_id,runtime.model_digest,revision.digest,targets,policy.digest)
    initial=runtime.model_digest
    candidate=train_specialization(runtime,run,rights,revision,train,heldout,
                                   scope="specialization",policy=policy)
    runtime.assert_model_unchanged()
    if runtime.model_digest!=initial or candidate["activation_authorized"] is not False:
        raise TrainingContractError("candidate generation changed base authority")
    return candidate


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feedback-export",type=Path,required=True)
    parser.add_argument("--feedback-sha256",required=True)
    parser.add_argument("--native-checkpoint",type=Path,required=True)
    parser.add_argument("--checkpoint-sha256",required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--run-id",required=True)
    parser.add_argument("--target",action="append",required=True)
    parser.add_argument("--rank",type=int,default=2)
    parser.add_argument("--steps",type=int,default=32)
    parser.add_argument("--max-tokens",type=int,default=65536)
    parser.add_argument("--approve-candidate-training",action="store_true")
    args=parser.parse_args(argv)
    if not args.approve_candidate_training:
        parser.error("explicit candidate-only training approval required")
    if args.output.exists() or args.output.is_symlink():
        parser.error("new output file required")
    data=json.loads(_read_pinned(args.feedback_export,args.feedback_sha256,MAX_EXPORT),
                    object_pairs_hook=_unique,parse_constant=_constant)
    validate_export(data)
    runtime=NativeLLMRuntime.restore_json(
        _read_pinned(args.native_checkpoint,args.checkpoint_sha256,MAX_CHECKPOINT),
        device_policy=DevicePolicy(requested="torch-cpu",allow_fallback=False),
    )
    policy=SpecializationPolicy(rank=args.rank,steps=args.steps,max_tokens=args.max_tokens)
    candidate=train_export(runtime,data,run_id=args.run_id,targets=tuple(args.target),policy=policy)
    pin=publish_candidate(candidate,args.output)
    print(json.dumps({"schema":"skeleton.jeeves.feedback-training-receipt.v1",
                     "candidate_sha256":candidate["candidate_sha256"],"file_sha256":pin,
                     "base_model_digest":runtime.model_digest,
                     "dataset_revision_digest":candidate["dataset_revision_digest"],
                     "heldout_base_nll":candidate["heldout_base_nll"],
                     "heldout_candidate_nll":candidate["heldout_candidate_nll"],
                     "activation_authorized":False,"independent_quality_certified":False},
                     sort_keys=True,allow_nan=False))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
