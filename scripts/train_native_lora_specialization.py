"""Explicit local native LoRA specialization from SHA-pinned checkpoint and governed data."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.model_runtime.runtime_contracts import DevicePolicy
from skeleton.ai.training.flgb_training_runtime import AdapterTrainingRun, DatasetRevision, DatasetRights
from skeleton.ai.training.native_lora_specialization import SpecializationPolicy, train_specialization, publish_candidate


def read(path,pin,limit):
    if path.is_symlink() or not path.is_file():
        raise ValueError("explicit local file required")
    with path.open("rb") as stream:
        raw=stream.read(limit+1)
    if len(raw)>limit or hashlib.sha256(raw).hexdigest()!=pin:
        raise ValueError("input custody mismatch")
    return raw


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--checkpoint",type=Path,required=True)
    p.add_argument("--checkpoint-sha256",required=True)
    p.add_argument("--dataset",type=Path,required=True)
    p.add_argument("--dataset-sha256",required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--device",choices=("torch-cpu","cuda","mps"),default="torch-cpu")
    a=p.parse_args(argv)
    rt=NativeLLMRuntime.restore_json(read(a.checkpoint,a.checkpoint_sha256,256*1024**2),
         device_policy=DevicePolicy(requested=a.device,allow_fallback=False))
    obj=json.loads(read(a.dataset,a.dataset_sha256,32*1024**2))
    candidate=train_specialization(rt,AdapterTrainingRun(**obj["run"]),DatasetRights(**obj["rights"]),
        DatasetRevision(**obj["revision"]),obj["train"],obj["heldout"],scope=obj["scope"],
        policy=SpecializationPolicy(**obj["policy"]))
    pin=publish_candidate(candidate,a.output)
    print(json.dumps({"status":"candidate_only","artifact_sha256":pin,"candidate_sha256":candidate["candidate_sha256"],
        "heldout_base_nll":candidate["heldout_base_nll"],"heldout_candidate_nll":candidate["heldout_candidate_nll"],
        "activation_authorized":False},sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
