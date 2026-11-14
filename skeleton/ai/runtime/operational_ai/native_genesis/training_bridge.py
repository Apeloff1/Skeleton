"""Real bootstrap-to-candidate SGD, using the already verified training engine."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import time

from .factory import GenesisInstance
from .errors import refuse
from .canonical import required_sha
from .checkpoint_store import publish_genesis
from ..native_candidate.factory import train_native, qualify_preflight


@dataclass(frozen=True, slots=True)
class NativeTrainingDelivery:
    genesis_publication: dict
    candidate_publication: dict
    original_model_sha256: str
    trained_model_sha256: str
    optimizer_steps: int
    elapsed_ms: int
    candidate_receipt_sha256: str

    def report(self) -> dict:
        return {
            "schema": "skeleton.native-genesis.train-delivery.v1",
            **{name:getattr(self,name) for name in self.__dataclass_fields__},
            "actual_native_sgd_completed": self.optimizer_steps > 0,
            "candidate_only": True,
            "independent_model_qualification": False,
            "production_authorized": False,
            "release_certified": False,
        }


def train_candidate_from_genesis(
    instance: GenesisInstance, *, trainer_code_sha256: str,
    bootstrap_directory: Path, candidate_directory: Path,
    state_directory: Path,
) -> NativeTrainingDelivery:
    if type(instance) is not GenesisInstance:
        refuse("training-native-genesis-required")
    required_sha(trainer_code_sha256, "training-code")
    if any(type(path) is not Path or not path.is_absolute()
           for path in (bootstrap_directory,candidate_directory,state_directory)):
        refuse("training-private-paths-required")
    # Publishing a genesis snapshot first creates an explicit immutable starting
    # point; partial training will leave only unqualified artifacts in custody.
    plan = instance.policy.for_candidate_training(
        instance.runtime.model_digest,instance.runtime.tokenizer.digest
    )
    # All source, rights, benchmark, tokenizer and capacity preflight gates
    # precede the first durable artifact creation.
    qualify_preflight(instance.runtime,plan)
    genesis_publication = publish_genesis(bootstrap_directory, instance)
    started = time.monotonic_ns()
    trained = train_native(
        instance.runtime, plan, code_sha256=trainer_code_sha256,
        output_directory=candidate_directory,
        state_directory=state_directory,
    )
    if trained.candidate_receipt.candidate_model_sha256 == instance.runtime.model_digest:
        refuse("training-no-model-change")
    return NativeTrainingDelivery(
        genesis_publication,
        {key:value for key,value in trained.publication.items()
         if key not in ("path", "private_path")},
        instance.runtime.model_digest,
        trained.candidate_receipt.candidate_model_sha256,
        trained.candidate_receipt.optimizer_steps,
        (time.monotonic_ns()-started)//1000000,
        trained.candidate_receipt.digest,
    )
