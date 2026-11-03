"""Trusted immutable checkpoint -> actual native challenge segment -> score."""
from __future__ import annotations
from pathlib import Path
from .private_checkpoint import restore
from .challenge_runner import evaluate_segment
from .challenge_score import score
from .latency_stats import summarize
from .canonical import require_sha
from .errors import reject


def probe(
    directory:Path,checkpoint_sha256:str,*,model_sha256:str,
    tokenizer_sha256:str,start:int=0,count:int=24,max_new_tokens:int=32,
)->dict:
    if type(directory) is not Path or not directory.is_absolute():
        reject("probe-trusted-directory")
    for label,value in (
        ("checkpoint",checkpoint_sha256),("model",model_sha256),
        ("tokenizer",tokenizer_sha256),
    ):
        require_sha(value,label)
    native=restore(
        directory,checkpoint_sha256,
        expected_model_sha256=model_sha256,
        expected_tokenizer_sha256=tokenizer_sha256,
    )
    result=evaluate_segment(
        native,start=start,count=count,max_new_tokens=max_new_tokens,
        expected_model_sha256=model_sha256,
    )
    return {
        "schema":"skeleton.native-supervised.probe-receipt.v1",
        "run":result.report(),
        "score":score(result),
        "performance":summarize(result),
        "source_complete":result.complete,
        "native_inference_executed":True,
        "release_certified":False,
    }
