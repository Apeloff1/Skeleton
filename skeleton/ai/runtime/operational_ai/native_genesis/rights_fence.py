"""Source rights and model boot cannot be confused with permission to deploy."""
from __future__ import annotations
from .source import GenesisSource
from .policy import GenesisPolicy
from .errors import refuse


def confirm(source: GenesisSource,policy: GenesisPolicy) -> dict:
    if type(source) is not GenesisSource or type(policy) is not GenesisPolicy:
        refuse("rights-fence-type")
    if not source.original_answers_valid or not source.benchmark_overlap_clear:
        refuse("rights-fence-source")
    if policy.license_id != "skeleton_original":
        refuse("rights-fence-license")
    if policy.training_scope != "offline_native_candidate_training":
        refuse("rights-fence-training-scope")
    if source.rights_sha256 == "0"*64:
        refuse("rights-fence-unverified")
    return {
        "schema":"skeleton.native-genesis.rights-fence.v1",
        "source_sha256":source.source_sha256,
        "rights_sha256":source.rights_sha256,
        "permitted_purpose":"offline_native_candidate_training",
        "external_weights_accepted":False,
        "synthetic_original_material":True,
        "serving_rights_granted":False,
    }
