"""Exact source/seed/segment parity before champion-candidate acceptance evidence."""
from __future__ import annotations
from pathlib import Path
from .private_checkpoint import restore
from .challenge_runner import evaluate_segment
from .paired_comparison import compare
from .challenge_score import score
from .errors import reject


def compare_checkpoints(
    champion_dir:Path,champion_checkpoint_sha256:str,
    champion_model_sha256:str,champion_tokenizer_sha256:str,
    candidate_dir:Path,candidate_checkpoint_sha256:str,
    candidate_model_sha256:str,candidate_tokenizer_sha256:str,
    *,start:int=0,count:int=24,max_new_tokens:int=32,
)->dict:
    if champion_model_sha256==candidate_model_sha256:
        reject("same-champion-candidate")
    champion=restore(
        champion_dir,champion_checkpoint_sha256,
        expected_model_sha256=champion_model_sha256,
        expected_tokenizer_sha256=champion_tokenizer_sha256,
    )
    candidate=restore(
        candidate_dir,candidate_checkpoint_sha256,
        expected_model_sha256=candidate_model_sha256,
        expected_tokenizer_sha256=candidate_tokenizer_sha256,
    )
    old=evaluate_segment(
        champion,start=start,count=count,max_new_tokens=max_new_tokens,
        expected_model_sha256=champion_model_sha256,
    )
    new=evaluate_segment(
        candidate,start=start,count=count,max_new_tokens=max_new_tokens,
        expected_model_sha256=candidate_model_sha256,
    )
    verdict=compare(old,new)
    if verdict["critical_regression"]:
        result="held-critical-regression"
    elif not verdict["full_768_case_comparison"]:
        result="held-partial-evaluation"
    elif not verdict["candidate_ahead_measured"]:
        result="held-no-improvement"
    else:
        result="pending-independent-review"
    return {
        "schema":"skeleton.native-supervised.compare-director.v1",
        "decision":result,
        "comparison":verdict,
        "champion_score":score(old),
        "candidate_score":score(new),
        "independent_verifier_approved":False,
        "production_authorized":False,
    }
