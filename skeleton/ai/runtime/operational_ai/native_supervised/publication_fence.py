"""No trained weights can be published without complete independent receipt proof."""
from __future__ import annotations
from .trainer import SupervisedResult
from .training_receipt import verify as verify_training
from .completion_guard import verify as verify_completion
from .canonical import digest
from .errors import reject


def admit(result:SupervisedResult)->dict:
    if type(result) is not SupervisedResult:
        reject("publish-real-training-result")
    proof=verify_training(result)
    alignment=verify_completion(result)
    return {
        "schema":"skeleton.native-supervised.publication-admission.v1",
        "model_sha256":proof.model_sha256,
        "tokenizer_sha256":proof.tokenizer_sha256,
        "checkpoint_sha256":proof.checkpoint_sha256,
        "evidence_sha256":digest({
            "training":proof.record(),
            "completion":alignment,
        }),
        "candidate_only":True,
        "release_certified":False,
    }
