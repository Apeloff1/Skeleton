"""Source-only and model-specific read-only genesis doctor."""
from __future__ import annotations
from .source import verify_source
from .vocabulary import build_vocabulary
from .vocab_coverage import inspect as coverage
from .architecture import estimate
from .policy import GenesisPolicy
from .vector_runner import run_all


def check(policy:GenesisPolicy,*,include_vectors:bool=True)->dict:
    source=verify_source()
    vocab=build_vocabulary(source,policy)
    capacity=estimate(policy,vocab)
    coverage_train=coverage(source,vocab,partition="train")
    coverage_validation=coverage(source,vocab,partition="validation")
    coverage_holdout=coverage(source,vocab,partition="holdout")
    result={
        "schema":"skeleton.native-genesis.doctor.v1",
        "policy":policy.record(),"source":source.report(),
        "vocabulary":vocab.report(),
        "architecture":capacity.report(),
        "train_token_coverage":coverage_train.report(),
        "validation_token_coverage":coverage_validation.report(),
        "holdout_token_coverage":coverage_holdout.report(),
        "training_ready":coverage_train.fraction_ppm>=policy.minimum_known_fraction_ppm,
        "checkpoint_created":False,
        "native_inference_executed":False,
        "release_certified":False,
    }
    if include_vectors:
        suite=run_all()
        result["policy_vectors"]={
            "cases":suite["cases"],"passed":suite["passed"],
            "failed":suite["failed"],"source_digest":suite["source_digest"],
        }
        result["training_ready"]=result["training_ready"] and suite["failed"]==0
    return result
