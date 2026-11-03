"""Genesis replay reconstitutes actual initial weights on the same source policy."""
from __future__ import annotations
from .factory import GenesisInstance, initialize_native
from .canonical import required_sha
from .errors import refuse


def compare_initialized(
    claimed:GenesisInstance,*,expected_checkpoint_sha256:str,
    allow_recompute:bool=False,
)->dict:
    if type(claimed) is not GenesisInstance:
        refuse("replay-native-instance")
    required_sha(expected_checkpoint_sha256,"replay-checkpoint")
    if claimed.checkpoint_sha256!=expected_checkpoint_sha256:
        refuse("replay-claimed-checkpoint")
    if allow_recompute is not True:
        return {
            "source_verified":True,
            "checkpoint_recomputation":False,
            "weights_reproducible":None,
            "release_certified":False,
        }
    # Do not assume cross-Python-version RNG/reduction stability. This
    # explicitly reruns the exact local implementation, then compares bytes.
    rebuilt=initialize_native(claimed.policy)
    if rebuilt.source.source_sha256!=claimed.source.source_sha256:
        refuse("replay-source-drift")
    if rebuilt.vocabulary.digest!=claimed.vocabulary.digest:
        refuse("replay-vocab-drift")
    if rebuilt.checkpoint_sha256!=claimed.checkpoint_sha256:
        refuse("replay-native-checkpoint-drift")
    return {
        "source_verified":True,
        "checkpoint_recomputation":True,
        "weights_reproducible":True,
        "release_certified":False,
    }
