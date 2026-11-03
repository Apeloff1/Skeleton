"""Synchronous operator-owned SFT pipeline; no async claims or automatic release."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from .bootstrap import initialize_aligned_model,AlignedGenesis
from .trainer import train,SupervisedResult
from .training_receipt import verify as verify_training
from .publication_fence import admit as admit_publication
from .gradient_audit import audit as audit_gradients
from .artifact_store import publish
from .canonical import digest,require_sha
from .errors import reject
from ..native_candidate.process_fence import model_training_fence


@dataclass(frozen=True,slots=True)
class Delivery:
    checkpoint_sha256:str
    candidate_model_sha256:str
    genesis_model_sha256:str
    source_sha256:str
    training_proof_sha256:str
    optimizer_steps:int
    publication:dict
    training:dict

    def report(self)->dict:
        return {
            "schema":"skeleton.native-supervised.delivery.v1",
            "checkpoint_sha256":self.checkpoint_sha256,
            "candidate_model_sha256":self.candidate_model_sha256,
            "genesis_model_sha256":self.genesis_model_sha256,
            "source_sha256":self.source_sha256,
            "training_proof_sha256":self.training_proof_sha256,
            "optimizer_steps":self.optimizer_steps,
            "publication":self.publication,
            "training":self.training,
            "actual_native_sft_completed":True,
            "challenge_quality_qualified":False,
            "production_authorized":False,
        }


def bootstrap(policy,*,directory:Path)->dict:
    from .policy import SupervisedPolicy
    if type(policy) is not SupervisedPolicy or type(directory) is not Path:
        reject("director-bootstrap-contract")
    instance=initialize_aligned_model(policy)
    return publish(
        directory,instance.initial_checkpoint,
        model_sha256=instance.runtime.model_digest,
        tokenizer_sha256=instance.runtime.tokenizer.digest,
        source_sha256=instance.source.corpus_sha256,
        kind="untrained-genesis",
    )


def deliver(
    policy,*,candidate_directory:Path,
    state_directory:Path,
)->Delivery:
    from .policy import SupervisedPolicy
    if type(policy) is not SupervisedPolicy:
        reject("director-policy")
    if type(candidate_directory) is not Path or not candidate_directory.is_absolute():
        reject("director-candidate-directory")
    if type(state_directory) is not Path or not state_directory.is_absolute():
        reject("director-state-directory")
    genesis=initialize_aligned_model(policy)
    # Lock the candidate model lifecycle before first SGD side effect.
    with model_training_fence(state_directory,genesis.runtime.model_digest):
        trained=train(genesis)
        proof=verify_training(trained)
        admit_publication(trained)
        audit_gradients(trained)
        proof_sha=digest(proof.record())
        publication=publish(
            candidate_directory,trained.candidate_checkpoint,
            model_sha256=trained.candidate_model_sha256,
            tokenizer_sha256=trained.tokenizer_sha256,
            source_sha256=genesis.source.corpus_sha256,
            kind="sft-candidate",
            training_receipt_sha256=proof_sha,
        )
    return Delivery(
        trained.candidate_checkpoint_sha256,trained.candidate_model_sha256,
        genesis.runtime.model_digest,genesis.source.corpus_sha256,
        proof_sha,trained.actual_optimizer_steps,
        publication,trained.receipt(),
    )
