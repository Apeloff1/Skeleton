"""outbox_delivery: typed existing-owner lifecycle assurance without invented evidence."""
from . import PROFILE
from skeleton.ai.runtime.operational_ai.offline_cognition.core.contracts import refuse
from skeleton.ai.runtime.operational_ai.offline_cognition.core.lifecycle_guard import (
    CheckEvidence,REQUIRED_CHECKS,inspect_source_install,inspect_boot_sequence,
    inspect_cold_restart,inspect_canonical_replay,inspect_outbox,proposed_ack,
    inspect_local_hash_journal,release_report,
)

def read_model_receipt(model_root,*,expected_model_sha256):
    return inspect_source_install(model_root,expected_model_sha256=expected_model_sha256)

def boot_order(chain):
    return inspect_boot_sequence(chain)

def restart(state_dir,scope):
    return inspect_cold_restart(state_dir,scope)

def replay(worker,scope,*,session_id,request_id,prompt,seed=0,temperature=0.8):
    return inspect_canonical_replay(worker,scope,session_id=session_id,
        request_id=request_id,prompt=prompt,seed=seed,temperature=temperature)

def pending(worker,scope,*,limit=32):
    return inspect_outbox(worker,scope,limit=limit)

def ack_intent(scope,*,event_key,event_sha256,request_id):
    return proposed_ack(scope,event_key=event_key,
                        event_sha256=event_sha256,request_id=request_id)

def audit(journal):
    return inspect_local_hash_journal(journal)

def release(*,commit_sha256,checks,model_rights_observed,native_inference_observed,
            laptop_device_observed,clean_install_observed,independent_review_observed):
    return release_report(commit_sha256=commit_sha256,checks=checks,
       model_rights_observed=model_rights_observed,
       native_inference_observed=native_inference_observed,
       laptop_device_observed=laptop_device_observed,
       clean_install_observed=clean_install_observed,
       independent_review_observed=independent_review_observed)

def contract():
    return {"family":PROFILE.name,"required_exact_head_gates":len(REQUIRED_CHECKS),
            "native_execution_requested":False,"outbox_ack_executed":False,
            "clean_windows_device_verified":False,"release_certified":False}
