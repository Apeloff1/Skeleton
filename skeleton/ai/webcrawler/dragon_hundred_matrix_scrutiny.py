"""One hundred independently attested mother-Dragon scrutiny matrices.

Matrix checks are specific audit questions, NOT 100 learned neural models.
Their attestation receipts must be signed by an externally provisioned reviewer
whose private key is unavailable to the Dragon. No proof is self-generated.
Passing checks permits a *proposal* for the existing governed shadow pipeline;
it does not directly create shadow/normal/hyper weights.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
import re
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from skeleton.ai.game_builder.contracts import canonical_digest, canonical_json

HEX = re.compile(r"[0-9a-f]{64}\Z")
AXES = {"source_identity": ["canonical_url","source_digest","publisher_identity","origin_trace","license_scope","capture_consent","retention_window","source_revision","capture_freshness","duplicate_detection"],"fact_provenance": ["exact_quote","claim_span","context_preserved","time_context","source_language","document_version","primary_reference","attribution","claim_type","citation_replay"],"independence": ["origin_groups","syndication_detection","cross_publication","different_method","common_dependency","citation_loop","source_influence","third_party_reviewer","witness_diversity","correlation_warning"],"contradiction": ["negation","opposing_claim","qualified_claim","counterexample","version_conflict","temporal_conflict","platform_conflict","uncertainty","alternative_explanation","unresolved_dispute"],"reproducibility": ["test_fixture","input_record","expected_output","runtime_version","hardware_profile","random_seed","determinism","failure_case","regression_test","replay_digest"],"game_compatibility": ["genre","era","console_limits","engine_api","rendering","physics","npc_behavior","audio","save_format","accessibility"],"legal_safety": ["copyright","trademark","patent","license_compatibility","personal_data","terms","robots","content_retention","code_provenance","distribution"],"code_quality": ["syntax","type_contract","security_test","dependency","resource_budget","concurrency","crash_recovery","observability","maintainability","portability"],"training_hygiene": ["training_license","data_leakage","holdout_isolation","prompt_injection","poisoning","privacy","deduplication","calibration","drift","human_signoff"],"operational_evidence": ["baseline_measurement","candidate_measurement","latency_p95","memory_peak","energy","accuracy_delta","negative_controls","rollback","bookmark_index","promotion_audit"]}
MATRIX_IDS = tuple(axis + "." + check
                   for axis, checks in AXES.items() for check in checks)
if len(AXES)!=10 or len(MATRIX_IDS)!=100 or len(set(MATRIX_IDS))!=100:
    raise AssertionError("mother scrutiny requires exactly 100 unique matrix IDs")


def _hex(value: str) -> str:
    if type(value) is not str or HEX.fullmatch(value) is None:
        raise ValueError("SHA-256 evidence identity required")
    return value


@dataclass(frozen=True)
class SignedMatrixFinding:
    matrix_id: str
    owner: str
    knowledge_digest: str
    evidence_digest: str
    independent_group_digests: tuple[str, ...]
    reviewer: str
    key_id: str
    issued_at: int
    expires_at: int
    verdict: str
    signature_hex: str

    def body(self) -> dict:
        return {
            "schema":"skeleton.dragon.mother_matrix_finding.v1",
            "matrix_id":self.matrix_id,"owner":self.owner,
            "knowledge_digest":self.knowledge_digest,
            "evidence_digest":self.evidence_digest,
            "independent_group_digests":list(self.independent_group_digests),
            "reviewer":self.reviewer,"key_id":self.key_id,
            "issued_at":self.issued_at,"expires_at":self.expires_at,
            "verdict":self.verdict,
        }


def scrutinize_one_hundred(
    owner: str, knowledge_digest: str, findings: tuple[SignedMatrixFinding,...], *,
    public_key: bytes, trusted_reviewer: str, key_id: str,
    now: int, require_groups: int = 2,
) -> dict:
    """Verify independently signed fact checks; no authority to train/promote.

    Missing, rejected, conflicting, stale or unsigned matrices block the
    *shadow-review proposal*. The real shadow/weight pipeline must separately
    authenticate source rights, human approval and out-of-sample improvement.
    """
    if type(owner) is not str or not 1<=len(owner)<=128:
        raise ValueError("bounded owner required")
    _hex(knowledge_digest)
    if (type(now) is not int or now<0 or
        type(require_groups) is not int or not 2<=require_groups<=8 or
        type(public_key) is not bytes or len(public_key)!=32 or
        type(trusted_reviewer) is not str or not trusted_reviewer or
        type(key_id) is not str or not key_id or
        type(findings) is not tuple or len(findings)>100):
        raise ValueError("trusted bounded independent scrutiny inputs required")
    verifier=Ed25519PublicKey.from_public_bytes(public_key)
    seen={}
    failed=[]
    for finding in findings:
        if not isinstance(finding,SignedMatrixFinding):
            raise TypeError("signed mother-matrix receipt required")
        if finding.matrix_id not in MATRIX_IDS or finding.matrix_id in seen:
            raise ValueError("unknown or duplicate matrix receipt")
        if (finding.owner!=owner or finding.knowledge_digest!=knowledge_digest
            or finding.reviewer!=trusted_reviewer or finding.key_id!=key_id):
            raise PermissionError("matrix attestation identity substitution")
        _hex(finding.evidence_digest)
        groups=finding.independent_group_digests
        if (not isinstance(groups,tuple) or not 2<=len(groups)<=8
            or groups!=tuple(sorted(set(groups)))):
            raise ValueError("bounded distinct reviewer-identified source groups required")
        for item in groups:
            _hex(item)
        if (type(finding.issued_at) is not int or type(finding.expires_at) is not int
            or finding.issued_at>now or not finding.issued_at<finding.expires_at
            or finding.expires_at-finding.issued_at>90*86400):
            raise ValueError("bounded attestation interval required")
        try:
            signature=bytes.fromhex(finding.signature_hex)
            verifier.verify(signature,canonical_json(finding.body()).encode())
        except (ValueError,TypeError,InvalidSignature) as exc:
            raise PermissionError("external reviewer signature invalid") from exc
        seen[finding.matrix_id]=finding
        if (finding.verdict!="pass" or now>=finding.expires_at
            or len(groups)<require_groups):
            failed.append(finding.matrix_id)
    missing=tuple(x for x in MATRIX_IDS if x not in seen)
    counts={axis:sum(
        f.matrix_id.startswith(axis+".") and f.matrix_id not in failed
        for f in seen.values()
    ) for axis in AXES}
    passed=len(seen)-len(failed)
    eligible=not missing and not failed and passed==100
    core={
        "schema":"skeleton.dragon.hundred_matrix_scrutiny.v1",
        "owner":owner,"knowledge_digest":knowledge_digest,
        "reviewer":trusted_reviewer,"key_id":key_id,
        "checked_at":now,"matrix_total":100,
        "attested_matrix_count":len(seen),
        "passed_matrix_count":passed,
        "axis_pass_counts":counts,
        "failed_matrix_ids":tuple(sorted(failed)),
        "missing_matrix_ids":missing,
        "shadow_review_proposal_eligible":eligible,
        "normal_weight_promotion_authorized":False,
        "hyperweight_promotion_authorized":False,
        "neural_training_authorized":False,
        "source_group_independence_externally_attested_not_proved":True,
        "external_source_rights_still_required":True,
    }
    return {**core,"report_digest":canonical_digest(core)}
