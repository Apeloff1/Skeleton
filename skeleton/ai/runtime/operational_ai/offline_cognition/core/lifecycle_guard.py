"""Source-bound installation, restart and exact-head release holds.

All model activation, native generation, SQLite outbox ACK and durable replay
remain under their pre-existing canonical owners. This module performs guarded
delegation/read-only source checks and never fabricates live-device results.
"""
from __future__ import annotations

from dataclasses import dataclass
from .contracts import Scope,identifier,sha,integer,refuse,fingerprint

REQUIRED_CHECKS=(
    "Merge Readiness","Backend Quality","App Foundation E2E",
    "Workflow Input Security","Sealed Context Guard","Artifact Policy",
    "Malware Gate","Repository Hygiene","Secret Scanning",
    "Dependency Review",
)
VALID_CONCLUSIONS=frozenset((
    "success","failure","cancelled","skipped","pending",
    "timed_out","neutral","action_required","stale","unknown",
))

def _canonical_identity(worker,scope):
    if type(scope) is not Scope:
        refuse("typed exact model/principal identity required")
    try:
        identity=worker.spine.identity
        values=(identity.tenant,identity.subject,identity.model_sha256,
                identity.tokenizer_sha256)
    except (AttributeError,TypeError):
        refuse("canonical supervised execution spine required")
    if values!=(scope.tenant,scope.subject,scope.model_sha256,scope.tokenizer_sha256):
        refuse("native worker identity changed or crossed principal")
    return identity

def inspect_source_install(model_root, *, expected_model_sha256):
    """Delegates actual shard+receipt verification to existing install owner."""
    sha(expected_model_sha256)
    if type(model_root) is not str or not model_root or "\x00" in model_root:
        refuse("operator-supplied installed-model directory required")
    from skeleton.ai.runtime.operational_ai.laptop_runtime.installation import source_receipt
    result=source_receipt(model_root,expected_model_sha256=expected_model_sha256,
                          require_rights=True)
    if result.model_sha256!=expected_model_sha256 or not result.content_verified:
        refuse("installed original bytes not verified")
    return {"schema":"offline-install-inspection.v1",
            "model_sha256":result.model_sha256,
            "archive_sha256":result.archive_sha256,
            "shards_verified_by_existing_installer":True,
            "model_rights_flag_observed":bool(result.rights_approved),
            "independent_license_legal_review_proved":False,
            "native_inference_executed":False,
            "release_certified":False}

def inspect_boot_sequence(chain):
    from skeleton.ai.runtime.operational_ai.laptop_runtime.boot_chain import BootChain
    if type(chain) is not BootChain:
        refuse("canonical boot proof chain required")
    report=chain.audit()
    if type(report) is not dict or report.get("stage_count",0)>6:
        refuse("invalid boot-chain audit")
    return {"stage_count":report["stage_count"],
            "stage_order_integrity_verified":True,
            "all_stages_present":report["complete"],
            "head_sha256":report["head_sha256"],
            "source_bytes_validated_by_this_function":False,
            "release_certified":False}

def inspect_cold_restart(state_dir,scope):
    if type(scope) is not Scope:
        refuse("exact native state scope required")
    if type(state_dir) is not str or not state_dir or "\x00" in state_dir:
        refuse("explicit existing state directory required")
    from skeleton.ai.runtime.operational_ai.laptop_runtime.restart_probe import inspect_restart
    result=inspect_restart(state_dir=state_dir,tenant=scope.tenant,
        subject=scope.subject,model_sha256=scope.model_sha256,
        tokenizer_sha256=scope.tokenizer_sha256)
    if result.get("native_restart_e2e_proved") is not False:
        refuse("read-only restart doctor claimed native resumption")
    return {"schema":"offline-cold-restart-inspection.v1",
            "scope_sha256":scope.digest(),
            "source_state_inspection":result,
            "second_native_generation_performed":False,
            "target_laptop_qualified":False}

def inspect_canonical_replay(worker,scope,*,session_id,request_id,prompt,
                             seed=0,temperature=0.8):
    """Only canonical SQLite replay; never call the model generation path."""
    _canonical_identity(worker,scope)
    from skeleton.ai.runtime.operational_ai.laptop_runtime.replay_probe import inspect_replay
    result=inspect_replay(worker,identifier(session_id),identifier(request_id),
                          prompt,seed=seed,temperature=temperature)
    if type(result) is not dict or result.get("no_second_generation") is not True:
        refuse("read-only canonical replay not proven")
    return {"scope_sha256":scope.digest(),"session_id":session_id,
            "request_id":request_id,"replay":result,
            "native_generation_invoked_by_inspector":False}

def inspect_outbox(worker,scope,*,limit=32):
    """Read authoritative pending events; never acknowledge without operator."""
    _canonical_identity(worker,scope)
    integer(limit,minimum=1,maximum=32)
    from skeleton.ai.runtime.operational_ai.laptop_runtime.outbox_delivery import DeliveryCursor
    events=DeliveryCursor(worker,maximum=limit).pending()
    if type(events) is not list or len(events)>limit:
        refuse("canonical outbox bounds violated")
    return {"schema":"offline-outbox-readonly.v1",
            "scope_sha256":scope.digest(),"pending_count":len(events),
            "events_returned_to_model":False,
            "event_ack_performed":False,"unverified_cross_subject_events_exposed":False}

def proposed_ack(scope,*,event_key,event_sha256,request_id):
    """Output an inert request; actual ACK remains with signed canonical owner."""
    if type(scope) is not Scope:
        refuse("operator model/subject scope required")
    identifier(event_key);sha(event_sha256);identifier(request_id)
    record={"schema":"offline-ack-proposal.v1",
            "scope_sha256":scope.digest(),"event_key":event_key,
            "event_sha256":event_sha256,"request_id":request_id}
    return {**record,"proposal_sha256":fingerprint(record),
            "acknowledged":False,"operator_signature_verified":False}

def inspect_local_hash_journal(journal):
    """In-memory journal integrity cannot certify durable SQLite append."""
    from .audit import Audit
    if type(journal) is not Audit:
        refuse("typed canonical diagnostic journal required")
    report=journal.verify()
    return {**report,"in_memory_integrity_verified":True,
            "durable_sqlite_integrity_proved":False,
            "external_signature_verified":False}

@dataclass(frozen=True, slots=True)
class CheckEvidence:
    workflow: str
    commit_sha256: str
    conclusion: str
    run_id: int

    def __post_init__(self):
        if self.workflow not in REQUIRED_CHECKS:
            refuse("unknown exact-head gate")
        sha(self.commit_sha256)
        if self.conclusion not in VALID_CONCLUSIONS:
            refuse("unknown workflow conclusion")
        integer(self.run_id,minimum=1)

def release_report(*,commit_sha256,checks,model_rights_observed,
                   native_inference_observed,laptop_device_observed,
                   clean_install_observed,independent_review_observed):
    """Strict-source release hold; caller-supplied statuses are not API proof."""
    sha(commit_sha256)
    if type(checks) not in (tuple,list) or len(checks)!=len(REQUIRED_CHECKS):
        refuse("exact ten final-head check records required")
    if any(type(x) is not CheckEvidence for x in checks):
        refuse("typed GitHub check source record required")
    if {x.workflow for x in checks}!=set(REQUIRED_CHECKS):
        refuse("missing or duplicated required workflow")
    if any(x.commit_sha256!=commit_sha256 for x in checks):
        refuse("superseded or cross-head CI evidence")
    observed=(model_rights_observed,native_inference_observed,
              laptop_device_observed,clean_install_observed,
              independent_review_observed)
    if any(type(x) is not bool for x in observed):
        refuse("explicit independent operator observation bits required")
    issues=[]
    for x in sorted(checks,key=lambda x:x.workflow):
        if x.conclusion!="success":
            issues.append(x.workflow+":"+x.conclusion)
    labels=("model-rights","native-gguf","target-laptop",
            "clean-install","independent-review")
    issues.extend(label for label,ok in zip(labels,observed) if not ok)
    # Even all input assertions saying "success" are untrusted until a
    # separate verifier reads exact GitHub API and licensed model/device bytes.
    issues.append("external-github-operator-and-license-attestation")
    summary=[{"workflow":x.workflow,"run_id":x.run_id,
              "conclusion":x.conclusion} for x in sorted(checks,key=lambda x:x.workflow)]
    body={"schema":"offline-ai-release-hold.v1","commit_sha256":commit_sha256,
          "gate_results":summary,"issues":issues}
    return {**body,"evidence_sha256":fingerprint(body),
            "all_declared_checks_success":all(x.conclusion=="success" for x in checks),
            "external_exact_head_source_proved":False,
            "release_certified":False,"safe_to_merge_automatically":False}
