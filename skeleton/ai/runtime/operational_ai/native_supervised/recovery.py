"""Uncertain write/SGD/cancel states always held for independent recovery."""
from __future__ import annotations
from .run_state import RunState
from .canonical import require_sha
from .errors import reject


def decide(
    state:RunState,*,checkpoint_sha256:str|None=None,
    verified_manifest:bool=False,pinned_audit_head:bool=False,
)->dict:
    if type(state) is not RunState:
        reject("recovery-state")
    if checkpoint_sha256 is not None:
        require_sha(checkpoint_sha256,"recovery-checkpoint")
    if type(verified_manifest) is not bool or type(pinned_audit_head) is not bool:
        reject("recovery-flag")
    if state.stage=="uncertain":
        reason="incomplete-or-ambiguous-side-effect"
    elif state.stage=="training":
        reason="incomplete-native-gradient"
    elif state.stage=="candidate_published":
        reason="candidate-must-be-independently-evaluated"
    else:
        reason="operator-review-required"
    return {
        "state":"held","reason":reason,
        "artifact_seen":checkpoint_sha256 is not None,
        "manifest_verified":verified_manifest,
        "audit_head_pinned":pinned_audit_head,
        "retry_same_run":False,
        "resume_training_automatically":False,
        "serving_activation":False,
    }
