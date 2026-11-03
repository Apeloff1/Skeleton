"""Read-only source, tokenizer and evaluation doctor; no model training."""
from __future__ import annotations
from .source import prepare_source
from .vocabulary import build_aligned_vocabulary
from .architecture import estimate
from .challenge_catalog import inventory as challenge_inventory
from .challenge_overlap import scan as overlap_scan,require_clear
from .policy import SupervisedPolicy
from .frames import paired_train
from .errors import reject


def diagnose(policy:SupervisedPolicy)->dict:
    if type(policy) is not SupervisedPolicy:
        reject("doctor-policy")
    source=prepare_source()
    vocabulary=build_aligned_vocabulary(source,policy)
    capacity=estimate(policy,vocabulary)
    pairs=paired_train(source.groups)
    if len(pairs)!=432:
        reject("doctor-training-source")
    challenge=challenge_inventory()
    if challenge["count"]!=768:
        reject("doctor-challenge-count")
    overlap=overlap_scan()
    require_clear(overlap)
    return {
        "schema":"skeleton.native-supervised.doctor.v1",
        "source":source.record(),
        "vocabulary":vocabulary.record(),
        "capacity":capacity.record(),
        "challenges":{
            "count":challenge["count"],
            "source_sha256":challenge["source_sha256"],
            "domains":challenge["domains"],
        },
        "contamination":overlap,
        "paired_training_examples":len(pairs),
        "same_chat_protocol_as_serving":True,
        "initial_weights_created":False,
        "optimizer_updates":0,
        "actual_challenges_evaluated":0,
        "release_certified":False,
    }
